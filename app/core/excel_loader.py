import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd

REQUIRED_COLUMNS = ["VoiceID", "台本ID", "区域"]
CN_TEXT_CANDIDATES = ["TOTTS_CN", "TOTTS", "CN", "Chinese", "TOTTS( CN )", "TOTTS（CN）"]
ENGLISH_TEXT_CANDIDATES = ["TOTTS_EN", "TOTTS_English", "English", "EN", "TOTTS_ENGLISH", "TOTTS(EN)"]
OPTIONAL_COLUMNS = ["Character", "Age", "Gender", "Emotion", "Text", "AI_Model", "Control Instruction", "ControlInstruction", "control_instruction", "控制指令"]
CONTROL_CANDIDATES = ["Control Instruction", "ControlInstruction", "control_instruction", "控制指令", "Control", "StylePrompt"]


@dataclass
class ExcelValidationResult:
    ok: bool
    missing_columns: List[str]
    sheet_names_with_required: List[str]
    selected_sheet: Optional[str]
    warning_messages: List[str]


def _clean_cols(cols):
    return [str(c).strip() for c in cols]


def _detect_col(df: pd.DataFrame, candidates: List[str]) -> str:
    cols = {str(c).strip().lower(): str(c).strip() for c in df.columns}
    for c in candidates:
        if c.lower() in cols:
            return cols[c.lower()]
    return ""


def discover_valid_sheets(excel_path: str) -> ExcelValidationResult:
    xls = pd.ExcelFile(excel_path)
    good = []
    warnings = []
    for s in xls.sheet_names:
        preview = pd.read_excel(excel_path, sheet_name=s, nrows=5)
        preview.columns = _clean_cols(preview.columns)
        miss = [c for c in REQUIRED_COLUMNS if c not in preview.columns]
        cn_col = _detect_col(preview, CN_TEXT_CANDIDATES)
        if not miss and cn_col:
            good.append(s)
    if not good:
        return ExcelValidationResult(False, REQUIRED_COLUMNS + ["TOTTS_CN(or TOTTS)", "TOTTS_EN(optional)"], [], None, ["未找到包含必需列的 sheet。至少需要: VoiceID, 区域, 台本ID, TOTTS_CN(或TOTTS)"])
    selected = good[0]
    if len(good) > 1:
        warnings.append(f"检测到多个可用 sheet: {', '.join(good)}")
    return ExcelValidationResult(True, [], good, selected, warnings)


def safe_filename(text: str) -> str:
    v = str(text).strip() if text is not None else ""
    if not v:
        return "UNKNOWN"
    v = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", v)
    v = re.sub(r'\s+', " ", v).strip(" .")
    return v or "UNKNOWN"


def load_excel_rows(excel_path: str, sheet_name: str) -> Tuple[pd.DataFrame, Dict[str, int], List[str]]:
    df = pd.read_excel(excel_path, sheet_name=sheet_name)
    df.columns = _clean_cols(df.columns)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"缺少必需列: {missing}")

    cn_col = _detect_col(df, CN_TEXT_CANDIDATES)
    en_col = _detect_col(df, ENGLISH_TEXT_CANDIDATES)
    control_col = _detect_col(df, CONTROL_CANDIDATES)
    if not cn_col:
        raise ValueError("缺少中文文本列：需要 TOTTS_CN（或兼容列 TOTTS）")

    df["_row_index"] = df.index + 2
    for c in OPTIONAL_COLUMNS:
        if c not in df.columns:
            df[c] = ""

    df["VoiceID"] = df["VoiceID"].astype(str).str.strip()
    df["台本ID"] = df["台本ID"].astype(str).str.strip()
    df["区域"] = df["区域"].fillna("UNKNOWN").astype(str).str.strip().replace("", "UNKNOWN")
    if "细分区域" not in df.columns:
        df["细分区域"] = ""
    df["细分区域"] = df["细分区域"].fillna("").astype(str).str.strip()

    df["TOTTS_CN"] = df[cn_col].fillna("").astype(str)
    df["TOTTS_EN"] = df[en_col].fillna("").astype(str) if en_col else ""
    df["CONTROL_INSTRUCTION"] = df[control_col].fillna("").astype(str) if control_col else ""

    # Backward compatibility for runner
    df["TOTTS"] = df["TOTTS_CN"]
    df["TOTTS_EN_AUTO"] = df["TOTTS_EN"]

    warnings = [f"检测到中文列: {cn_col}"]
    if control_col:
        warnings.append(f"检测到控制指令列: {control_col}")
    if en_col:
        warnings.append(f"检测到英文列: {en_col}")
    else:
        warnings.append("未检测到英文列，EN 导出将自动跳过。")

    dup = df["台本ID"][df["台本ID"] != ""].duplicated(keep=False)
    if dup.any():
        warnings.append("检测到重复台本ID，请注意覆盖策略。")

    stats = {
        "total_rows": int(len(df)),
        "valid_rows": int(((df["VoiceID"] != "") & (df["台本ID"] != "") & (df["TOTTS_CN"].str.strip() != "")).sum()),
        "voice_count": int(df["VoiceID"][df["VoiceID"] != ""].nunique()),
    }
    return df, stats, warnings
