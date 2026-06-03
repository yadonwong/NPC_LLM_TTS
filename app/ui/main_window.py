import os
from pathlib import Path
import pandas as pd
from PySide6.QtCore import Qt, QThread, QAbstractTableModel, QSortFilterProxyModel
from PySide6.QtGui import QAction
from PySide6.QtWidgets import *

from app.core.config import AppConfig, save_settings
from app.core.excel_loader import discover_valid_sheets, load_excel_rows
from app.core.model_downloader import ModelDownloader
from app.core.tts_batch_runner import BatchRunner
from app.core.voice_cache import VoiceCacheManager
from app.core.voxcpm_manager import VoxCPMManager
from app.core.index_tts_manager import IndexTTSManager


class PandasModel(QAbstractTableModel):
    def __init__(self, df): super().__init__(); self.df=df.copy()
    def rowCount(self, p=None): return len(self.df)
    def columnCount(self, p=None): return len(self.df.columns)
    def data(self, i, role=Qt.DisplayRole):
        return str(self.df.iat[i.row(), i.column()]) if i.isValid() and role==Qt.DisplayRole else None
    def headerData(self, s, o, role=Qt.DisplayRole):
        if role!=Qt.DisplayRole: return None
        return self.df.columns[s] if o==Qt.Horizontal else str(s+1)
    def update_cell(self, r, c, v):
        if c in self.df.columns and 0<=r<len(self.df):
            k=self.df.columns.get_loc(c); self.df.iat[r,k]=v; self.dataChanged.emit(self.index(r,k), self.index(r,k))


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig, logger, log_emitter):
        super().__init__(); self.config=config; self.logger=logger; self.log_emitter=log_emitter
        self.log_emitter.log_signal.connect(self.append_log)
        self.setWindowTitle('NPC LLM TTS'); self.resize(1550, 920)
        self.df=pd.DataFrame(); self.table_model=None; self.proxy=None; self.thread=None; self.runner=None
        self.downloader=ModelDownloader(self.config.model_path); self.cache=VoiceCacheManager(self.config.voice_cache_dir, self.config.ref_dir); self.vox=VoxCPMManager(self.config.model_path, self.logger); self.index_tts=IndexTTSManager(self.config.index_model_path, self.logger)
        self._menu(); self._ui(); self.status_model()

    def _menu(self):
        m=self.menuBar(); fm=m.addMenu('文件')
        a=QAction('导入 Excel', self); a.triggered.connect(self.choose_excel); fm.addAction(a)
        s=QAction('设置', self); s.triggered.connect(lambda: QMessageBox.information(self,'设置','设置在左侧卡片')); fm.addAction(s)
        ab=QAction('关于', self); ab.triggered.connect(lambda: QMessageBox.information(self,'关于','NPC LLM TTS\n© Yadon Wong, 2026')); m.addAction(ab)

    def _ui(self):
        root=QWidget(); v=QVBoxLayout(root)
        h=QHBoxLayout(); self.lb_model=QLabel('模型: 未检测'); self.lb_dev=QLabel(f'设备: {self.config.device}')
        b1=QPushButton('打开 Output'); b1.clicked.connect(lambda:self.open_dir(self.config.output_dir))
        b2=QPushButton('打开 VoiceCache'); b2.clicked.connect(lambda:self.open_dir(self.config.voice_cache_dir))
        h.addWidget(QLabel('NPC LLM TTS')); h.addStretch(); h.addWidget(self.lb_model); h.addWidget(self.lb_dev); h.addWidget(b1); h.addWidget(b2); v.addLayout(h)

        sp=QSplitter(Qt.Horizontal)
        L=QWidget(); ll=QVBoxLayout(L)
        g1=QGroupBox('项目输入'); i1=QVBoxLayout(g1); x=QHBoxLayout(); self.excel=QLineEdit(self.config.last_excel_path); bx=QPushButton('选择 Excel'); bx.clicked.connect(self.choose_excel); x.addWidget(self.excel); x.addWidget(bx)
        self.lb_stats=QLabel('总行数:0 | 有效行数:0 | VoiceID:0'); i1.addLayout(x); i1.addWidget(self.lb_stats); ll.addWidget(g1)
        g2=QGroupBox('生成设置'); f=QFormLayout(g2)
        self.dev=QComboBox(); self.dev.addItems(['auto','cpu','mps','cuda','cuda:0','cuda:1']); self.dev.setCurrentText(self.config.device)
        self.engine=QComboBox(); self.engine.addItems(['voxcpm','indextts']); self.engine.setCurrentText(getattr(self.config,'tts_engine','voxcpm')); self.engine.currentTextChanged.connect(lambda _: self.status_model())
        self.cfg=QLineEdit(str(self.config.cfg_value)); self.steps=QLineEdit(str(self.config.inference_timesteps)); self.seed=QLineEdit(str(self.config.random_seed))
        self.den=QCheckBox('load_denoiser'); self.den.setChecked(self.config.load_denoiser)
        self.pol=QComboBox(); self.pol.addItems(['skip','overwrite','version']); self.pol.setCurrentText(self.config.overwrite_policy)
        self.reuse=QCheckBox('复用 VoiceID 参考'); self.reuse.setChecked(self.config.reuse_voice_cache)
        self.regen=QCheckBox('每次重新生成参考'); self.regen.setChecked(not self.config.reuse_voice_cache); self.regen.stateChanged.connect(lambda: self.reuse.setChecked(not self.regen.isChecked()))
        f.addRow('TTS引擎',self.engine); f.addRow('device',self.dev); f.addRow('cfg_value',self.cfg); f.addRow('inference_timesteps',self.steps); f.addRow('random_seed',self.seed); f.addRow('',self.den); f.addRow('覆盖策略',self.pol); f.addRow('',self.reuse); f.addRow('',self.regen); ll.addWidget(g2)
        g3=QGroupBox('音频设置'); a=QFormLayout(g3)
        self.norm=QCheckBox('启用响度归一化'); self.norm.setChecked(self.config.enable_loudness_normalization)
        self.lufs=QLineEdit(str(self.config.target_lufs)); self.tp=QLineEdit(str(self.config.true_peak_ceiling))
        a.addRow('输出格式', QLabel('48kHz / 24Bit / Mono')); a.addRow('',self.norm); a.addRow('目标 LUFS',self.lufs); a.addRow('True Peak',self.tp); ll.addWidget(g3)
        hb=QHBoxLayout(); c1=QPushButton('清空全部缓存'); c1.clicked.connect(lambda: QMessageBox.information(self,'完成',f'已清理 {self.cache.clear_all()} 个')); c2=QPushButton('清空选中 VoiceID'); c2.clicked.connect(self.clear_one); hb.addWidget(c1); hb.addWidget(c2); ll.addLayout(hb); ll.addStretch()

        tabs=QTabWidget()
        self.tabs=tabs
        C=QWidget(); cl=QVBoxLayout(C); self.search=QLineEdit(); self.search.setPlaceholderText('搜索...'); self.search.textChanged.connect(lambda t: self.proxy and self.proxy.setFilterFixedString(t)); self.table=QTableView(); self.table.setAlternatingRowColors(True); cl.addWidget(self.search); cl.addWidget(self.table)
        tabs.addTab(C, 'Excel预览')

        single_tab=QWidget(); sl=QFormLayout(single_tab)
        self.sg_voice_id=QLineEdit(); self.sg_script_id=QLineEdit(); self.sg_region=QLineEdit(); self.sg_subregion=QLineEdit()
        self.sg_control=QLineEdit(); self.sg_totts_cn=QPlainTextEdit(); self.sg_totts_cn.setPlaceholderText('中文文本 TOTTS_CN')
        self.sg_ref_wav_path=QLineEdit(); self.sg_ref_wav_path.setPlaceholderText('可选：选择参考音频文件（wav/flac/mp3/m4a）')
        self.sg_ref_wav_btn=QPushButton('选择音色参考文件')
        self.sg_ref_wav_btn.clicked.connect(self.pick_single_reference_wav)
        self.sg_totts_en=QPlainTextEdit(); self.sg_totts_en.setPlaceholderText('英文文本 TOTTS_EN（可选）')
        self.sg_count=QSpinBox(); self.sg_count.setRange(1, 9999); self.sg_count.setValue(1)
        sl.addRow('VoiceID', self.sg_voice_id); sl.addRow('台本ID', self.sg_script_id); sl.addRow('区域', self.sg_region); sl.addRow('细分区域', self.sg_subregion)
        ref_row=QHBoxLayout(); ref_row.addWidget(self.sg_ref_wav_path); ref_row.addWidget(self.sg_ref_wav_btn)
        ref_wrap=QWidget(); ref_wrap.setLayout(ref_row)
        sl.addRow('音色参考文件', ref_wrap)
        sl.addRow('控制指令', self.sg_control); sl.addRow('TOTTS_CN', self.sg_totts_cn); sl.addRow('TOTTS_EN', self.sg_totts_en); sl.addRow('生成条数', self.sg_count)
        tabs.addTab(single_tab, '单句生成')

        ref_tab=QWidget(); rfl=QVBoxLayout(ref_tab)
        rb=QHBoxLayout(); self.ref_voice_filter=QLineEdit(); self.ref_voice_filter.setPlaceholderText('筛选 VoiceID')
        btn_import_ref=QPushButton('为选中VoiceID导入参考音频'); btn_import_ref.clicked.connect(self.import_ref_for_selected)
        btn_import_ref_current=QPushButton('为单句 VoiceID 导入参考音频'); btn_import_ref_current.clicked.connect(self.import_ref_for_single_voice)
        btn_delete_ref=QPushButton('删除选中音色'); btn_delete_ref.clicked.connect(self.delete_ref_for_selected)
        btn_refresh_ref=QPushButton('刷新参考状态'); btn_refresh_ref.clicked.connect(self.refresh_ref_table)
        rb.addWidget(self.ref_voice_filter); rb.addWidget(btn_import_ref); rb.addWidget(btn_import_ref_current); rb.addWidget(btn_delete_ref); rb.addWidget(btn_refresh_ref)
        self.ref_table=QTableWidget(); self.ref_table.setColumnCount(3); self.ref_table.setHorizontalHeaderLabels(['VoiceID','参考文件','状态']); self.ref_table.horizontalHeader().setStretchLastSection(True)
        self.ref_voice_filter.textChanged.connect(self.refresh_ref_table)
        rfl.addLayout(rb); rfl.addWidget(self.ref_table)
        tabs.addTab(ref_tab, '参考音色管理')

        R=QWidget(); rl=QVBoxLayout(R)
        self.lb_total=QLabel('总任务数: 0'); self.lb_done=QLabel('已完成: 0'); self.lb_skip=QLabel('跳过: 0'); self.lb_fail=QLabel('失败: 0'); self.lb_cur=QLabel('当前: -')
        self.pb=QProgressBar(); self.pb2=QProgressBar()
        for w in [self.lb_total,self.lb_done,self.lb_skip,self.lb_fail,self.lb_cur,QLabel('总进度'),self.pb,QLabel('当前进度'),self.pb2]: rl.addWidget(w)
        ah=QHBoxLayout(); self.bs=QPushButton('Start'); self.bs.setObjectName('StartButton'); self.bp=QPushButton('Pause'); self.br=QPushButton('Resume'); self.bt=QPushButton('Stop')
        self.bs.clicked.connect(self.start); self.bp.clicked.connect(lambda: self.runner and self.runner.pause()); self.br.clicked.connect(lambda: self.runner and self.runner.resume()); self.bt.clicked.connect(lambda: self.runner and self.runner.stop())
        for b in [self.bs,self.bp,self.br,self.bt]: ah.addWidget(b)
        rl.addLayout(ah); rl.addStretch()

        sp.addWidget(L); sp.addWidget(tabs); sp.addWidget(R); sp.setSizes([420,760,360]); v.addWidget(sp)
        self.log=QPlainTextEdit(); self.log.setReadOnly(True); v.addWidget(QLabel('日志')); v.addWidget(self.log,1)
        self.setCentralWidget(root)

    def append_log(self, m): self.log.appendPlainText(m)
    def open_dir(self, p):
        Path(p).mkdir(parents=True, exist_ok=True)
        if os.name=='nt': os.startfile(p)
        else:
            import subprocess; subprocess.Popen(['open', p])
    def status_model(self):
        engine=self.engine.currentText() if hasattr(self,'engine') else getattr(self.config,'tts_engine','voxcpm')
        if engine=='indextts':
            p=Path(self.config.index_model_path)
            ok=(p/'config.yaml').exists() and (p/'qwen0.6bemo4-merge'/'model.safetensors').exists()
            state='已就绪' if ok else '未安装'
            self.lb_model.setText(f'当前引擎: IndexTTS | 状态: {state}')
        else:
            state='已就绪' if self.downloader.is_ready() else '未安装'
            self.lb_model.setText(f'当前引擎: VoxCPM2 | 状态: {state}')

    def choose_excel(self):
        p,_=QFileDialog.getOpenFileName(self,'选择 Excel',self.config.last_excel_path or '', 'Excel Files (*.xlsx *.xls)')
        if not p:return
        self.excel.setText(p); self.config.last_excel_path=p; self.load_excel(p); self.save_cfg()

    def load_excel(self, p):
        d=discover_valid_sheets(p)
        if not d.ok: QMessageBox.critical(self,'错误','\n'.join(d.warning_messages)); return
        sheet=d.selected_sheet
        if len(d.sheet_names_with_required)>1:
            sheet,ok=QInputDialog.getItem(self,'选择 Sheet','Sheet:',d.sheet_names_with_required,0,False)
            if not ok:return
        df,st,w=load_excel_rows(p,sheet); df['状态']='Pending'; cmap=self.cache.status_map(df['VoiceID'].astype(str).unique()); df['参考状态']=df['VoiceID'].astype(str).map(cmap)
        self.df=df
        preview_df=df[['VoiceID','区域','TOTTS_CN','TOTTS_EN','状态','参考状态']].copy()
        self.table_model=PandasModel(preview_df); self.proxy=QSortFilterProxyModel(self); self.proxy.setSourceModel(self.table_model); self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive); self.proxy.setFilterKeyColumn(-1); self.table.setModel(self.proxy)
        self.refresh_ref_table()
        self.lb_stats.setText(f"总行数:{st['total_rows']} | 有效行数:{st['valid_rows']} | VoiceID:{st['voice_count']} | 导出语言: CN+EN")
        self.lb_total.setText(f"总任务数: {st['valid_rows']}")
        if w: QMessageBox.warning(self,'警告','\n'.join(w))

    def clear_one(self):
        if self.df.empty:return
        i=self.table.currentIndex()
        if not i.isValid(): QMessageBox.warning(self,'提示','请选择一行'); return
        r=self.proxy.mapToSource(i).row() if self.proxy else i.row(); vid=str(self.table_model.df.iloc[r]['VoiceID']); ok=self.cache.clear_one(vid)
        self.refresh_ref_table(); self.refresh_main_ref_status()
        QMessageBox.information(self,'完成',f'{vid}: {"成功" if ok else "未找到"}')

    def refresh_main_ref_status(self):
        if self.table_model is None: return
        cmap=self.cache.status_map(self.table_model.df['VoiceID'].astype(str).unique())
        self.table_model.df['参考状态']=self.table_model.df['VoiceID'].astype(str).map(cmap)
        self.table_model.layoutChanged.emit()

    def refresh_ref_table(self):
        voice_ids=[]
        if self.table_model is not None and 'VoiceID' in self.table_model.df.columns:
            voice_ids=sorted(set(self.table_model.df['VoiceID'].astype(str).tolist()))
        q=self.ref_voice_filter.text().strip().lower() if hasattr(self,'ref_voice_filter') else ''
        if q:
            voice_ids=[v for v in voice_ids if q in v.lower()]
        self.ref_table.setRowCount(len(voice_ids))
        for r,vid in enumerate(voice_ids):
            p=self.cache.get_effective_reference_path(vid)
            st='已有参考' if p else '未设置'
            self.ref_table.setItem(r,0,QTableWidgetItem(vid))
            self.ref_table.setItem(r,1,QTableWidgetItem(str(p) if p else ''))
            self.ref_table.setItem(r,2,QTableWidgetItem(st))
        self.refresh_single_ref_options()

    def refresh_single_ref_options(self):
        if not hasattr(self,'sg_ref_voice'):
            return
        cur=self.sg_ref_voice.currentData()
        self.sg_ref_voice.blockSignals(True)
        self.sg_ref_voice.clear()
        self.sg_ref_voice.addItem('不使用参考音色（自动）', '')
        self.sg_ref_voice.addItem('使用当前 VoiceID 的已有参考', '__AUTO_BY_VOICE_ID__')
        for vid in self.cache.list_reference_voice_ids():
            self.sg_ref_voice.addItem(f'{vid}', vid)
        idx=self.sg_ref_voice.findData(cur)
        if idx>=0:
            self.sg_ref_voice.setCurrentIndex(idx)
        self.sg_ref_voice.blockSignals(False)

    def pick_single_reference_wav(self):
        p,_=QFileDialog.getOpenFileName(self,'选择参考音频', '', 'Audio Files (*.wav *.flac *.mp3 *.m4a)')
        if not p:
            return
        self.sg_ref_wav_path.setText(p)

    def import_ref_for_selected(self):
        if self.ref_table.rowCount()==0:
            QMessageBox.warning(self,'提示','请先导入 Excel'); return
        row=self.ref_table.currentRow()
        if row<0:
            QMessageBox.warning(self,'提示','请在参考音色管理页选择一个 VoiceID'); return
        vid_item=self.ref_table.item(row,0)
        if vid_item is None:
            return
        vid=vid_item.text().strip()
        file_path,_=QFileDialog.getOpenFileName(self,'选择参考音频', '', 'Audio Files (*.wav *.flac *.mp3 *.m4a)')
        if not file_path:
            return
        try:
            target=self.cache.import_manual_reference(vid, file_path)
            self.append_log(f'已导入参考音色: {vid} -> {target}')
            self.refresh_ref_table(); self.refresh_main_ref_status()
            QMessageBox.information(self,'完成',f'已为 {vid} 设置参考音色')
        except Exception as e:
            QMessageBox.critical(self,'导入失败',str(e))

    def ensure_voice_id_visible_in_ref_table(self, voice_id: str):
        voice_id=str(voice_id or '').strip()
        if not voice_id:
            return
        q=self.ref_voice_filter.text().strip().lower() if hasattr(self,'ref_voice_filter') else ''
        if q and q not in voice_id.lower():
            self.ref_voice_filter.setText('')
        for r in range(self.ref_table.rowCount()):
            item=self.ref_table.item(r,0)
            if item and item.text().strip()==voice_id:
                self.ref_table.setCurrentCell(r,0)
                self.ref_table.scrollToItem(item)
                return
        row=self.ref_table.rowCount()
        self.ref_table.insertRow(row)
        p=self.cache.get_effective_reference_path(voice_id)
        st='已有参考' if p else '未设置'
        self.ref_table.setItem(row,0,QTableWidgetItem(voice_id))
        self.ref_table.setItem(row,1,QTableWidgetItem(str(p) if p else ''))
        self.ref_table.setItem(row,2,QTableWidgetItem(st))
        self.ref_table.setCurrentCell(row,0)

    def import_ref_for_single_voice(self):
        vid=self.sg_voice_id.text().strip() if hasattr(self,'sg_voice_id') else ''
        if not vid:
            QMessageBox.warning(self,'提示','请先在单句生成里填写 VoiceID'); return
        self.ensure_voice_id_visible_in_ref_table(vid)
        self.import_ref_for_selected()

    def delete_ref_for_selected(self):
        if self.ref_table.rowCount()==0:
            QMessageBox.warning(self,'提示','请先导入 Excel'); return
        row=self.ref_table.currentRow()
        if row<0:
            QMessageBox.warning(self,'提示','请在参考音色管理页选择一个 VoiceID'); return
        vid_item=self.ref_table.item(row,0)
        if vid_item is None:
            return
        vid=vid_item.text().strip()
        ok=self.cache.clear_one(vid)
        self.refresh_ref_table(); self.refresh_main_ref_status()
        QMessageBox.information(self,'完成',f'{vid}: {"删除成功" if ok else "未找到参考音色"}')

    def build_single_generate_df(self):
        voice_id=self.sg_voice_id.text().strip()
        script_id=self.sg_script_id.text().strip()
        region=self.sg_region.text().strip()
        subregion=self.sg_subregion.text().strip()
        control=self.sg_control.text().strip()
        totts_cn=self.sg_totts_cn.toPlainText().strip()
        totts_en=self.sg_totts_en.toPlainText().strip()
        count=int(self.sg_count.value())
        selected_ref_wav=(self.sg_ref_wav_path.text().strip() if hasattr(self,'sg_ref_wav_path') else '')

        if not voice_id or not script_id or not region or not totts_cn:
            raise ValueError('请至少填写 VoiceID、台本ID、区域、TOTTS_CN')

        rows=[]
        for n in range(1, count+1):
            sid=f"{script_id}_{n:03d}" if count>1 else script_id
            rows.append({
                '_row_index': n+1,
                'VoiceID': voice_id,
                '台本ID': sid,
                '区域': region,
                '细分区域': subregion,
                'TOTTS_CN': totts_cn,
                'TOTTS_EN': totts_en,
                'CONTROL_INSTRUCTION': control,
                'REFERENCE_WAV_PATH': selected_ref_wav,
                'TOTTS': totts_cn,
                'TOTTS_EN_AUTO': totts_en,
                '状态': 'Pending',
            })
        return pd.DataFrame(rows)

    def apply_cfg(self):
        c=self.config; c.tts_engine=self.engine.currentText(); c.device=self.dev.currentText(); c.cfg_value=float(self.cfg.text()); c.inference_timesteps=int(self.steps.text()); c.load_denoiser=self.den.isChecked(); c.random_seed=self.seed.text().strip(); c.enable_loudness_normalization=self.norm.isChecked(); c.target_lufs=float(self.lufs.text()); c.true_peak_ceiling=float(self.tp.text()); c.overwrite_policy=self.pol.currentText(); c.reuse_voice_cache=self.reuse.isChecked() and not self.regen.isChecked()
    def save_cfg(self): save_settings(self.config)

    def start(self):
        try: self.apply_cfg(); self.save_cfg()
        except Exception as e: QMessageBox.critical(self,'参数错误',str(e)); return

        use_single_tab = hasattr(self,'tabs') and self.tabs.currentIndex()==1
        if use_single_tab:
            try:
                run_df=self.build_single_generate_df()
            except Exception as e:
                QMessageBox.warning(self,'提示',str(e)); return
        else:
            if self.df.empty: QMessageBox.warning(self,'提示','请先导入 Excel'); return
            run_df=self.df

        self.bs.setEnabled(False)
        self.pb2.setRange(0,0)
        self.lb_cur.setText('当前: 正在准备模型...')

        engine=getattr(self.config,'tts_engine','voxcpm')
        model_manager=None

        if engine=='voxcpm':
            self.lb_model.setText('VoxCPM2: 下载/检查中'); self.append_log('步骤 1/3: 正在检查/下载 VoxCPM2 模型...')
            ok,msg=self.downloader.ensure_model(self.logger, progress_cb=self.append_log)
            if not ok:
                self.pb2.setRange(0,1); self.pb2.setValue(0); self.bs.setEnabled(True)
                self.lb_model.setText('VoxCPM2: 下载失败'); QMessageBox.critical(self,'模型下载失败',msg); return
            self.lb_model.setText('VoxCPM2: 加载中'); self.append_log('步骤 2/3: 正在加载 VoxCPM2 模型...')
            try: dev=self.vox.load_model(device=self.config.device, load_denoiser=self.config.load_denoiser); self.lb_dev.setText(f'设备: {dev}')
            except Exception as e:
                self.pb2.setRange(0,1); self.pb2.setValue(0); self.bs.setEnabled(True)
                QMessageBox.critical(self,'模型加载失败',str(e)); return
            self.lb_model.setText('VoxCPM2: 已加载')
            model_manager=self.vox
        else:
            p=Path(self.config.index_model_path)
            required=[
                p/'config.yaml',
                p/'gpt.pth',
                p/'s2mel.pth',
                p/'qwen0.6bemo4-merge'/'model.safetensors',
            ]
            missing=[str(x) for x in required if not x.exists()]
            offline_missing=self.index_tts.check_offline_dependencies()
            if missing or offline_missing:
                self.pb2.setRange(0,1); self.pb2.setValue(0); self.bs.setEnabled(True)
                self.lb_model.setText('IndexTTS: 缺少模型文件')
                msg='缺少以下文件：\n\n'
                if missing:
                    msg += '\n'.join(missing) + '\n\n'
                if offline_missing:
                    msg += '离线依赖缺失：\n' + '\n'.join(offline_missing) + '\n\n'
                    msg += '建议先联网下载一次（MaskGCT + BigVGAN），或提前将依赖缓存到本机。\n\n'
                msg += '请先将 IndexTTS-2 模型完整下载到 models/IndexTTS-2 后重试。'
                QMessageBox.warning(self,'IndexTTS 模型不完整', msg)
                return
            self.lb_model.setText('IndexTTS: 加载中'); self.append_log('步骤 1/2: 正在加载 IndexTTS 模型...')
            try: dev=self.index_tts.load_model(device=self.config.device, load_denoiser=False); self.lb_dev.setText(f'设备: {dev}')
            except Exception as e:
                self.pb2.setRange(0,1); self.pb2.setValue(0); self.bs.setEnabled(True)
                QMessageBox.critical(self,'模型加载失败',str(e)); return
            self.lb_model.setText('IndexTTS: 已加载')
            model_manager=self.index_tts

        self.append_log('步骤 3/3: 模型就绪，开始批处理...')
        self.pb2.setRange(0,1); self.pb2.setValue(1)

        self.thread=QThread(self); self.runner=BatchRunner(run_df,self.config,model_manager,self.cache,self.logger); self.runner.moveToThread(self.thread)
        self.thread.started.connect(self.runner.run); self.runner.row_status.connect(self.on_row); self.runner.progress.connect(self.on_prog); self.runner.current.connect(lambda v,s,o: self.lb_cur.setText(f'当前: {v} / {s}\n{o}')); self.runner.finished.connect(self.on_finish); self.thread.start()

    def on_row(self, r, st, msg):
        self.table_model.update_cell(r,'状态',st)
        if msg: self.append_log(f'Row {r+1} {st}: {msg}')

    def on_prog(self, d, t): self.pb.setMaximum(max(t,1)); self.pb.setValue(d); self.pb2.setMaximum(1); self.pb2.setValue(1)

    def on_finish(self, s):
        self.bs.setEnabled(True)
        self.lb_done.setText(f"已完成: {s.get('done',0)}"); self.lb_skip.setText(f"跳过: {s.get('skipped',0)}"); self.lb_fail.setText(f"失败: {s.get('failed',0)}")
        QMessageBox.information(self,'任务完成',f"总数:{s.get('total')}\n完成:{s.get('done')}\n失败:{s.get('failed')}\n报告:{s.get('report_path')}")
        if self.thread: self.thread.quit(); self.thread.wait(3000)
