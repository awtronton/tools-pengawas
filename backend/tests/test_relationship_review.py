"""Isolated metadata integration tests; never uses the configured warehouse database."""
import asyncio
import copy
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest
from unittest.mock import patch

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, event, func, select, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import StaticPool

from database import table_service as db
from services.relationship_cardinality_service import estimate_candidate_cardinality
from services.relationship_freshness_service import material_signature, validate_freshness
from services.relationship_review_service import (
    ReviewConflict, decide_candidate, get_candidate_review, get_candidate_review_history,
)
from services.relationship_scoring_service import score_candidate


class ReviewTests(unittest.TestCase):
    def setUp(self):
        socket = os.environ.get('REVIEW_TEST_PG_SOCKET')
        if socket:
            if not socket.startswith('/tmp/ojk-review-pg.'):
                raise RuntimeError('Only an isolated temporary PostgreSQL socket is allowed')
            url = URL.create('postgresql+psycopg2', database='postgres',
                             query={'host': socket, 'port': '55439'})
            admin = create_engine(url)
            schema_name = 'review_test_' + uuid.uuid4().hex
            with admin.begin() as con:
                con.execute(text('CREATE SCHEMA ' + schema_name))
            def clean_schema():
                with admin.begin() as con:
                    con.execute(text('DROP SCHEMA ' + schema_name + ' CASCADE'))
                admin.dispose()
            self.addCleanup(clean_schema)
            self.engine = create_engine(url, connect_args={'options': '-csearch_path=' + schema_name})
        else:
            self.engine = create_engine('sqlite://', poolclass=StaticPool,
                                        connect_args={'check_same_thread': False})
        db.metadata.create_all(self.engine)
        self.engine_patch = patch.object(db, 'engine', self.engine)
        self.ensure_patch = patch.object(db, 'ensure_internal_tables', lambda: None)
        self.engine_patch.start()
        self.ensure_patch.start()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.engine_patch.stop)
        self.addCleanup(self.ensure_patch.stop)
        schema = MetaData()
        for name in ('review_source', 'review_target'):
            Table(name, schema, Column('bank_id', String), Column('bulan', Integer), Column('tahun', Integer))
        schema.create_all(self.engine)
        with self.engine.begin() as con:
            con.execute(db.table_state_table.insert(), [dict(table_name=t, data_version=1)
                for t in ('review_source', 'review_target')])
            con.execute(db.column_settings_table.insert().values(
                table_name='review_source', column_name='bank_id', is_masked=True))
        self.profiles = {}
        for table in ('review_source', 'review_target'):
            for column in ('bank_id', 'bulan', 'tahun'):
                distinct = 100 if table == 'review_source' else 50
                self.profiles[table, column] = db.upsert_column_profile(dict(
                    table_name=table, column_name=column, data_type='VARCHAR' if column == 'bank_id' else 'INTEGER',
                    type_family='text' if column == 'bank_id' else 'numeric', profile_mode='full',
                    source_data_version=1, row_count_estimate=100, sample_row_count=100,
                    sample_non_null_count=100, sample_distinct_count=distinct, null_ratio=0,
                    distinct_ratio=distinct / 100, avg_length=5, value_fingerprint=['hashed-only']))
        self.candidates = [self.seed_candidate(column, i) for i, column in enumerate(('bank_id', 'bulan', 'tahun'), 1)]

    def seed_candidate(self, column, number):
        candidate = db.upsert_relationship_candidate(dict(
            candidate_key=f'{number:064x}', table_pair_key='a' * 64,
            source_table='review_source', target_table='review_target',
            source_column=column, target_column=column,
            source_profile_version=1, target_profile_version=1,
            source_data_version=1, target_data_version=1,
            source_type_family='text' if column == 'bank_id' else 'numeric',
            target_type_family='text' if column == 'bank_id' else 'numeric',
            name_similarity=1, fingerprint_overlap=1, discovery_score=.97,
            detector_version='metadata_candidate_v1', last_seen_job_id=1,
            evidence=dict(same_system_key=True, fingerprint={'comparable': True},
                          source_distinct_ratio=1, target_distinct_ratio=.5,
                          source_null_ratio=0, target_null_ratio=0)))
        self.analyse(candidate)
        return candidate

    def analyse(self, candidate):
        sp = self.profiles[candidate['source_table'], candidate['source_column']]
        tp = self.profiles[candidate['target_table'], candidate['target_column']]
        score = score_candidate(candidate, sp, tp)
        score['last_scored_job_id'] = 1
        score = db.upsert_relationship_candidate_score(score)
        estimate = estimate_candidate_cardinality(candidate, sp, tp, score)
        estimate['last_estimated_job_id'] = 1
        db.upsert_relationship_cardinality_estimate(estimate)

    def payload(self, ids=(1,), **changes):
        detail = get_candidate_review(ids[0], ids)
        return dict(candidate_ids=list(ids), expected_revision=detail['review_revision'],
                    request_key='test-request', reviewed_by='Reviewer Test', review_note='Evidence diperiksa',
                    cardinality='one_to_many', composite_cardinality_confirmed=len(ids) > 1,
                    **changes)

    def count(self, table):
        with self.engine.connect() as con:
            return con.scalar(select(func.count()).select_from(table))

    def test_single_approval_retry_masking_and_immutable_history(self):
        detail = get_candidate_review(1)
        self.assertTrue(detail['can_approve'])
        self.assertTrue(detail['candidates'][0]['columns']['source']['masked'])
        self.assertNotIn('value_fingerprint', detail['candidates'][0]['profiles']['source'])
        payload = self.payload()
        result = decide_candidate(1, 'approved', payload)
        replay = decide_candidate(1, 'approved', payload)
        self.assertTrue(replay['replayed'])
        self.assertEqual(result['review'], replay['review'])
        self.assertEqual(self.count(db.relationships_table), 1)
        before = get_candidate_review_history(1)
        relation = db.get_table_relationships()[0]
        self.assertTrue(relation['source_masked'])
        db.delete_table_relationship(relation['id'])
        db.mark_table_profile_stale('review_source')
        self.assertEqual(before, get_candidate_review_history(1))
        self.assertEqual(before[0]['reviewer_source'], 'self_declared')
        self.assertEqual(self.count(db.relationship_reviews_table), 1)

    def test_payload_key_reuse_conflicts(self):
        payload = self.payload()
        decide_candidate(1, 'approved', payload)
        payload['review_note'] = 'different'
        with self.assertRaises(ReviewConflict):
            decide_candidate(1, 'approved', payload)

    def test_second_reviewer_cannot_promote_same_revision(self):
        payload = self.payload()
        other = dict(payload, request_key='second-request')
        decide_candidate(1, 'approved', payload)
        with self.assertRaises(ReviewConflict):
            decide_candidate(1, 'approved', other)
        self.assertEqual(self.count(db.relationships_table), 1)

    def test_composite_explicit_confirmation_and_atomic_pair_promotion(self):
        payload = self.payload((1, 2, 3))
        payload['composite_cardinality_confirmed'] = False
        with self.assertRaises(ValueError):
            decide_candidate(1, 'approved', payload)
        self.assertEqual(self.count(db.relationships_table), 0)
        payload['composite_cardinality_confirmed'] = True
        result = decide_candidate(1, 'approved', payload)
        self.assertEqual(self.count(db.relationship_columns_table), 3)
        self.assertEqual(self.count(db.relationship_review_candidates_table), 3)
        self.assertEqual(get_candidate_review_history(2)[0]['id'], result['review']['id'])
        self.assertEqual(db.get_table_relationships()[0]['pair_count'], 3)

    def test_reverse_composite_duplicate_and_reactivation_blocked(self):
        relation = db.create_table_relationship(relationship_name='Existing', source_table='review_target',
            target_table='review_source', cardinality='many_to_one', column_pairs=[
                dict(source_column=c, target_column=c) for c in ('tahun', 'bulan', 'bank_id')])
        with self.assertRaises(ReviewConflict):
            decide_candidate(1, 'approved', self.payload((1, 2, 3)))
        self.assertEqual(self.count(db.relationship_reviews_table), 0)
        db.update_table_relationship(relation['id'], is_active=False)
        decide_candidate(1, 'approved', self.payload((1, 2, 3)))
        with self.assertRaises(ValueError):
            db.update_table_relationship(relation['id'], is_active=True)

    def test_rollback_after_relationship_insert(self):
        create = db.create_table_relationship
        def fail_after_create(**kwargs):
            create(**kwargs)
            raise RuntimeError('simulated audit-stage failure')
        with patch.object(db, 'create_table_relationship', fail_after_create):
            with self.assertRaises(RuntimeError):
                decide_candidate(1, 'approved', self.payload())
        self.assertEqual(self.count(db.relationships_table), 0)
        self.assertEqual(self.count(db.relationship_columns_table), 0)
        self.assertEqual(self.count(db.relationship_reviews_table), 0)
        self.assertEqual(get_candidate_review(1)['candidates'][0]['candidate']['status'], 'pending')

    def test_stale_and_data_version_conflicts_even_without_stale_flag(self):
        payload = self.payload()
        with self.engine.begin() as con:
            con.execute(db.table_state_table.update().where(
                db.table_state_table.c.table_name == 'review_source').values(data_version=2))
        detail = get_candidate_review(1)
        self.assertFalse(detail['can_approve'])
        self.assertIn('source_data_version_changed', detail['candidates'][0]['freshness']['reasons'])
        with self.assertRaises(ReviewConflict):
            decide_candidate(1, 'approved', payload)
        with self.assertRaises(ValueError):
            self.analyse(self.candidates[0])

    def test_reprofile_invalidates_candidate_score_and_cardinality(self):
        profile = dict(self.profiles['review_source', 'bank_id'])
        db.upsert_column_profile(profile)
        detail = get_candidate_review(1)['candidates'][0]
        for name in ('candidate', 'quality_score', 'cardinality_estimate'):
            self.assertTrue(detail[name]['is_stale'])
        self.assertIn('source_profile_version_changed', detail['freshness']['reasons'])

    def test_quality_rescore_invalidates_estimate_and_legacy_lineage_blocks(self):
        with self.engine.begin() as con:
            estimate = con.execute(select(db.relationship_cardinality_estimates_table).where(
                db.relationship_cardinality_estimates_table.c.candidate_id == 1)).mappings().one()
            evidence = dict(estimate['evidence'])
            evidence.pop('quality_score_signature')
            con.execute(db.relationship_cardinality_estimates_table.update().where(
                db.relationship_cardinality_estimates_table.c.candidate_id == 1).values(evidence=evidence))
        self.assertIn('cardinality_quality_lineage_missing', get_candidate_review(1)['candidates'][0]['freshness']['reasons'])
        self.analyse(self.candidates[0])
        self.assertTrue(get_candidate_review(1)['can_approve'])
        with self.engine.begin() as con:
            con.execute(db.relationship_candidate_scores_table.update().where(
                db.relationship_candidate_scores_table.c.candidate_id == 1).values(confidence_score=.12))
        self.assertIn('cardinality_quality_changed', get_candidate_review(1)['candidates'][0]['freshness']['reasons'])

    def test_rejection_suppressed_on_rerun_reopens_only_material_evidence(self):
        decide_candidate(1, 'rejected', self.payload())
        self.assertEqual(len(db.get_relationship_candidates()), 2)
        self.assertEqual(len(db.get_relationship_candidates(status='rejected')), 1)
        candidate = dict(self.candidates[0])
        candidate['last_seen_job_id'] = 2
        saved = db.upsert_relationship_candidate(candidate)
        self.assertEqual(saved['status'], 'rejected')
        profile = dict(self.profiles['review_source', 'bank_id'])
        updated = db.upsert_column_profile(profile)
        candidate['source_profile_version'] = updated['profile_version']
        saved = db.upsert_relationship_candidate(candidate)
        self.assertEqual(saved['status'], 'rejected')
        candidate['evidence'] = dict(candidate['evidence'], source_distinct_ratio=.7)
        saved = db.upsert_relationship_candidate(candidate)
        self.assertEqual(saved['status'], 'pending')
        self.assertFalse(get_candidate_review(1)['can_approve'])
        self.assertEqual(len(get_candidate_review_history(1)), 1)

    def test_rejection_note_and_override_note_required(self):
        payload = self.payload()
        payload['review_note'] = ''
        with self.assertRaises(ValueError):
            decide_candidate(1, 'rejected', payload)
        payload['cardinality'] = 'many_to_many'
        with self.assertRaises(ValueError):
            decide_candidate(1, 'approved', payload)

    def test_candidate_direction_change_invalidates_score_even_same_versions(self):
        with self.engine.begin() as con:
            con.execute(db.relationship_candidates_table.update().where(
                db.relationship_candidates_table.c.id == 1).values(
                    source_table='review_target', target_table='review_source'))
        reasons = get_candidate_review(1)['candidates'][0]['freshness']['reasons']
        self.assertIn('quality_candidate_evidence_changed', reasons)
        self.assertIn('cardinality_candidate_evidence_changed', reasons)

    def test_masking_change_since_review_conflicts(self):
        payload = self.payload()
        with self.engine.begin() as con:
            con.execute(db.column_settings_table.update().values(is_masked=False))
        with self.assertRaises(ReviewConflict):
            decide_candidate(1, 'approved', payload)
        self.assertEqual(self.count(db.relationships_table), 0)

    def test_bounded_group_and_wrong_table_group(self):
        with self.assertRaises(ValueError):
            get_candidate_review(1, range(1, 14))
        with self.engine.begin() as con:
            con.execute(db.relationship_candidates_table.update().where(
                db.relationship_candidates_table.c.id == 2).values(target_table='other_table'))
        with self.assertRaises(ValueError):
            get_candidate_review(1, [2])

    def test_review_reads_do_not_scan_warehouse_rows(self):
        queries = []
        def record(_con, _cursor, statement, _parameters, _context, _executemany):
            queries.append(statement.lower())
        event.listen(self.engine, 'before_cursor_execute', record)
        get_candidate_review(1, [2, 3])
        self.assertFalse(any('from review_source' in q or 'from review_target' in q for q in queries))

    def test_shared_validator_rejects_every_version_dependency(self):
        s = get_candidate_review(1)['candidates'][0]
        profiles = {(s['candidate'][side + '_table'], s['candidate'][side + '_column']): s['profiles'][side]
                    for side in ('source', 'target')}
        for name in ('quality_score', 'cardinality_estimate'):
            for field in ('source_profile_version', 'target_profile_version', 'source_data_version', 'target_data_version'):
                with self.subTest(name=name, field=field):
                    changed = copy.deepcopy(s)
                    changed[name][field] += 1
                    result = validate_freshness(changed['candidate'], profiles, changed['data_versions'],
                                               changed['quality_score'], changed['cardinality_estimate'])
                    self.assertFalse(result['is_fresh'])

    @unittest.skipUnless(os.environ.get('REVIEW_TEST_PG_SOCKET'), 'requires isolated PostgreSQL')
    def test_concurrent_reviewers_promote_exactly_once(self):
        payload = self.payload()
        barrier = Barrier(2)
        def approve(key):
            barrier.wait(timeout=5)
            try:
                return decide_candidate(1, 'approved', dict(payload, request_key=key))
            except ReviewConflict:
                return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(approve, ['reviewer-a', 'reviewer-b']))
        self.assertEqual(outcomes.count('conflict'), 1)
        self.assertEqual(self.count(db.relationships_table), 1)
        self.assertEqual(self.count(db.relationship_reviews_table), 1)

    @unittest.skipUnless(os.environ.get('REVIEW_TEST_PG_SOCKET'), 'requires isolated PostgreSQL')
    def test_concurrent_manual_reverse_creation_and_approval(self):
        payload = self.payload()
        barrier = Barrier(2)
        def create(approve):
            barrier.wait(timeout=5)
            try:
                if approve:
                    decide_candidate(1, 'approved', payload)
                else:
                    db.create_table_relationship(relationship_name='Manual reverse',
                        source_table='review_target', target_table='review_source',
                        source_column='bank_id', target_column='bank_id', cardinality='many_to_one')
                return 'created'
            except ValueError:
                return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(create, [True, False]))
        self.assertEqual(sorted(outcomes), ['conflict', 'created'])
        self.assertEqual(self.count(db.relationships_table), 1)

    def test_api_contract_openapi_and_conflicts(self):
        from main import app
        schema = app.openapi()
        self.assertIn('/relationship-intelligence/candidates/{candidate_id}/approve', schema['paths'])
        async def call(method, path, payload=None):
            messages = []
            body = json.dumps(payload).encode() if payload is not None else b''
            async def receive():
                return {"type": "http.request", "body": body, "more_body": False}
            async def send(message):
                messages.append(message)
            await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                       "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
                       "query_string": b'', "root_path": '', "server": ('test', 80),
                       "client": ('127.0.0.1', 1234), "headers": [(b'content-type', b'application/json')]}, receive, send)
            code = next(m['status'] for m in messages if m['type'] == 'http.response.start')
            data = json.loads(b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body'))
            return code, data
        async def exercise():
            code, data = await call('GET', '/relationship-intelligence/candidates/1/review')
            self.assertEqual(code, 200)
            payload = self.payload()
            code, data = await call('POST', '/relationship-intelligence/candidates/1/approve', payload)
            self.assertEqual(code, 200, data)
            code, data = await call('POST', '/relationship-intelligence/candidates/1/approve', payload)
            self.assertTrue(data['replayed'])
            code, data = await call('POST', '/relationship-intelligence/candidates/1/reject', payload)
            self.assertEqual(code, 409)
            code, data = await call('GET', '/relationship-intelligence/candidates/999/review')
            self.assertEqual(code, 404)
        asyncio.run(exercise())


if __name__ == '__main__':
    unittest.main()
