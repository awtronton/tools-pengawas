import {
  Network,
} from 'lucide-react'

const cardinalityContent = {
  one_to_one: {
    label: 'One-to-One (1:1)',
    source: '1',
    target: '1',
    description:
      'Satu row pada Source hanya berhubungan dengan satu row pada Target, dan sebaliknya.',
    example:
      'Contoh: satu profil bank ↔ satu master bank.',
  },
  one_to_many: {
    label: 'One-to-Many (1:N)',
    source: '1',
    target: 'N',
    description:
      'Satu row pada Source dapat berhubungan dengan banyak row pada Target.',
    example:
      'Contoh: satu bank → banyak laporan bulanan.',
  },
  many_to_one: {
    label: 'Many-to-One (N:1)',
    source: 'N',
    target: '1',
    description:
      'Banyak row pada Source dapat mengarah ke satu row pada Target.',
    example:
      'Contoh: banyak laporan bulanan → satu bank.',
  },
  many_to_many: {
    label: 'Many-to-Many (N:N)',
    source: 'N',
    target: 'N',
    description:
      'Banyak row pada Source dapat berhubungan dengan banyak row pada Target.',
    example:
      'Contoh: banyak debitur ↔ banyak fasilitas pada data penghubung.',
  },
}

function Marker({
  x,
  side,
  type,
}) {
  const direction =
    side === 'left' ? -1 : 1

  if (type === '1') {
    return (
      <g
        stroke="currentColor"
        strokeWidth="2"
        fill="none"
      >
        <line
          x1={x}
          y1="34"
          x2={x}
          y2="54"
        />
        <line
          x1={x + 5 * direction}
          y1="34"
          x2={x + 5 * direction}
          y2="54"
        />
      </g>
    )
  }

  return (
    <g
      stroke="currentColor"
      strokeWidth="2"
      fill="none"
      strokeLinecap="round"
    >
      <line
        x1={x}
        y1="44"
        x2={x + 12 * direction}
        y2="31"
      />
      <line
        x1={x}
        y1="44"
        x2={x + 12 * direction}
        y2="44"
      />
      <line
        x1={x}
        y1="44"
        x2={x + 12 * direction}
        y2="57"
      />
    </g>
  )
}

function CardinalityHelper({
  cardinality,
}) {
  const content =
    cardinalityContent[cardinality] ||
    cardinalityContent.one_to_many

  return (
    <div className="tp-cardinality-helper">
      <div className="tp-cardinality-helper-heading">
        <div>
          <Network size={13} />

          <span>
            {content.label}
          </span>
        </div>

        <small>
          General relationship illustration
        </small>
      </div>

      <div className="tp-cardinality-helper-visual">
        <svg
          viewBox="0 0 520 88"
          role="img"
          aria-label={content.label}
        >
          <rect
            x="18"
            y="18"
            width="118"
            height="52"
            rx="8"
            className="tp-cardinality-box"
          />

          <text
            x="77"
            y="38"
            textAnchor="middle"
            className="tp-cardinality-box-caption"
          >
            SOURCE
          </text>

          <text
            x="77"
            y="58"
            textAnchor="middle"
            className="tp-cardinality-box-value"
          >
            {content.source}
          </text>

          <line
            x1="144"
            y1="44"
            x2="376"
            y2="44"
            className="tp-cardinality-line"
          />

          <g className="tp-cardinality-marker">
            <Marker
              x={154}
              side="right"
              type={content.source}
            />

            <Marker
              x={366}
              side="left"
              type={content.target}
            />
          </g>

          <rect
            x="384"
            y="18"
            width="118"
            height="52"
            rx="8"
            className="tp-cardinality-box"
          />

          <text
            x="443"
            y="38"
            textAnchor="middle"
            className="tp-cardinality-box-caption"
          >
            TARGET
          </text>

          <text
            x="443"
            y="58"
            textAnchor="middle"
            className="tp-cardinality-box-value"
          >
            {content.target}
          </text>
        </svg>
      </div>

      <p>
        {content.description}
      </p>

      <small className="tp-cardinality-example">
        {content.example}
      </small>
    </div>
  )
}

export default CardinalityHelper
