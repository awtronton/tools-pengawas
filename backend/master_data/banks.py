BANKS = [
    {"bank_id": "7110001", "bank_name": "Bank Umum Arunika", "bank_type": "bank_umum"},
    {"bank_id": "7120001", "bank_name": "BPR Bahari", "bank_type": "bpr"},
    {"bank_id": "7120002", "bank_name": "BPR Cakrawala", "bank_type": "bpr"},
    {"bank_id": "7120003", "bank_name": "BPR Danapati", "bank_type": "bpr"},
    {"bank_id": "7120004", "bank_name": "BPR Ekantara", "bank_type": "bpr"},
    {"bank_id": "7120005", "bank_name": "BPR Fajar Nusantara", "bank_type": "bpr"},
    {"bank_id": "7120006", "bank_name": "BPR Garuda Sentosa", "bank_type": "bpr"},
    {"bank_id": "7120007", "bank_name": "BPR Harmoni", "bank_type": "bpr"},
    {"bank_id": "7120008", "bank_name": "BPR Indraprima", "bank_type": "bpr"},
    {"bank_id": "7120009", "bank_name": "BPR Jaya Mandiri", "bank_type": "bpr"},
    {"bank_id": "7120010", "bank_name": "BPR Kencana", "bank_type": "bpr"},
    {"bank_id": "7120011", "bank_name": "BPR Lintas Dana", "bank_type": "bpr"},
    {"bank_id": "7120012", "bank_name": "BPR Mahardika", "bank_type": "bpr"},
    {"bank_id": "7120013", "bank_name": "BPR Nawasena", "bank_type": "bpr"},
    {"bank_id": "7120014", "bank_name": "BPR Optima Nusantara", "bank_type": "bpr"},
    {"bank_id": "7120015", "bank_name": "BPR Pusaka Dana", "bank_type": "bpr"},
    {"bank_id": "7120016", "bank_name": "BPR Rajawali", "bank_type": "bpr"},
    {"bank_id": "7120017", "bank_name": "BPR Samudra", "bank_type": "bpr"},
    {"bank_id": "7120018", "bank_name": "BPR Tirta Kencana", "bank_type": "bpr"},
    {"bank_id": "7120019", "bank_name": "BPR Utama Sejahtera", "bank_type": "bpr"},
    {"bank_id": "7120020", "bank_name": "BPR Wijaya Dana", "bank_type": "bpr"},
]

_BANKS_BY_NAME = {
    item["bank_name"].strip().casefold(): item
    for item in BANKS
}


def get_all_banks():
    return BANKS.copy()


def get_bank_by_name(bank_name: str):
    key = str(bank_name or "").strip().casefold()

    if not key:
        raise ValueError("Nama bank wajib dipilih.")

    bank = _BANKS_BY_NAME.get(key)

    if not bank:
        raise ValueError(
            f"Nama bank '{bank_name}' tidak terdaftar pada master bank."
        )

    return bank.copy()
