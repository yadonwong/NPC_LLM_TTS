import subprocess
from pathlib import Path
from typing import Optional


class ModelDownloader:
    def __init__(self, model_dir: str):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.complete_marker = self.model_dir / ".download_complete"

    def is_ready(self) -> bool:
        return self.complete_marker.exists()

    def clone_voxcpm_repo(self, repo_dir: str, logger) -> None:
        repo_path = Path(repo_dir)
        if repo_path.exists() and any(repo_path.iterdir()):
            logger.info("VoxCPM repo already exists: %s", repo_path)
            return
        repo_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["git", "clone", "https://github.com/OpenBMB/VoxCPM", str(repo_path)]
        logger.info("Cloning VoxCPM repository...")
        subprocess.check_call(cmd)

    def _download_hf(self, logger):
        from huggingface_hub import snapshot_download

        logger.info("Downloading model from HuggingFace: openbmb/VoxCPM2")
        snapshot_download(repo_id="openbmb/VoxCPM2", local_dir=str(self.model_dir), local_dir_use_symlinks=False)

    def _download_ms(self, logger):
        from modelscope.hub.snapshot_download import snapshot_download

        logger.info("Downloading model from ModelScope: OpenBMB/VoxCPM2")
        snapshot_download(model_id="OpenBMB/VoxCPM2", local_dir=str(self.model_dir))

    def ensure_model(self, logger, progress_cb=None) -> tuple[bool, str]:
        if self.is_ready():
            return True, "模型已就绪"
        try:
            if progress_cb:
                progress_cb("正在从 HuggingFace 下载模型...")
            self._download_hf(logger)
        except Exception as hf_err:
            logger.error("HuggingFace download failed: %s", hf_err)
            try:
                if progress_cb:
                    progress_cb("HuggingFace 失败，正在尝试 ModelScope...")
                self._download_ms(logger)
            except Exception as ms_err:
                logger.error("ModelScope download failed: %s", ms_err)
                return False, f"下载失败：HF={hf_err}; MS={ms_err}"
        self.complete_marker.write_text("ok", encoding="utf-8")
        return True, "模型下载完成"
