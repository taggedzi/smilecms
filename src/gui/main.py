from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from ..config import Config, load_config
from ..verify import VerificationReport
from ..htmlvalidate import HtmlValidationReport
from ..jsvalidate import JsValidationReport
from ..media import audit_media
from ..ingest import load_documents
from ..gui_service import (
    MRU,
    BuildOptions,
    BuildResult,
    add_mru,
    audit_media_json_payload,
    check_environment,
    diff_yaml,
    discover_project,
    get_mru,
    load_config_with_text,
    render_config_yaml,
    render_verification_text,
    save_config,
    scaffold,
    start_preview_server,
    stop_preview_server,
    validate_html_safe,
    validate_js_safe,
    verify_links,
)


class Worker(QtCore.QObject):
    done = QtCore.Signal(object)
    error = QtCore.Signal(str)
    log = QtCore.Signal(str)
    progress = QtCore.Signal(str, int, int)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    @QtCore.Slot()
    def run(self):
        try:
            result = self._fn(*self._args, **self._kwargs)
            self.done.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SmileCMS GUI")
        self.resize(1100, 760)

        self._current_project: Optional[Path] = None
        self._current_config: Optional[Config] = None
        self._current_config_path: Optional[Path] = None
        self._current_config_text: str = ""
        self._preview_handle = None

        self._tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(self._tabs)

        self._init_start_tab()
        self._init_config_tab()
        self._init_new_content_tab()
        self._init_build_tab()
        self._init_test_tab()
        self._init_preview_tab()
        self._init_audit_tab()

        self._refresh_mru()
        self._update_env_panel()

    # ------------- Start Tab -------------
    def _init_start_tab(self):
        w = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(w)

        header = QtWidgets.QLabel("Select or initialize a project")
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(header)

        # Environment status
        self._env_status = QtWidgets.QTextEdit()
        self._env_status.setReadOnly(True)
        self._env_status.setMinimumHeight(140)
        layout.addWidget(self._env_status)

        # Project theme status
        self._project_theme_status = QtWidgets.QLabel("")
        layout.addWidget(self._project_theme_status)

        env_btns = QtWidgets.QHBoxLayout()
        self._open_hf_btn = QtWidgets.QPushButton("Open HF cache folder")
        self._open_hf_btn.clicked.connect(self._open_hf_cache)
        env_btns.addWidget(self._open_hf_btn)
        env_btns.addStretch(1)
        layout.addLayout(env_btns)

        # MRU
        mru_box = QtWidgets.QGroupBox("Recent projects")
        mru_layout = QtWidgets.QVBoxLayout(mru_box)
        self._mru_list = QtWidgets.QListWidget()
        self._mru_list.itemDoubleClicked.connect(self._open_selected_mru)
        mru_layout.addWidget(self._mru_list)
        layout.addWidget(mru_box)

        btns = QtWidgets.QHBoxLayout()
        open_btn = QtWidgets.QPushButton("Open Project…")
        open_btn.clicked.connect(self._choose_project)
        init_btn = QtWidgets.QPushButton("Init New Project…")
        init_btn.clicked.connect(self._init_project_dialog)
        btns.addWidget(open_btn)
        btns.addWidget(init_btn)
        btns.addStretch(1)
        layout.addLayout(btns)

        self._tabs.addTab(w, "Project")

    def _refresh_mru(self):
        mru: MRU = get_mru()
        self._mru_list.clear()
        for p in mru.paths:
            item = QtWidgets.QListWidgetItem(str(p))
            self._mru_list.addItem(item)

    def _update_env_panel(self):
        status = check_environment()
        self._last_env_status = status
        lines = [
            f"Python: {status.python_version} ({status.executable})",
            f"Node.js: {'OK '+(status.node_version or '') if status.js_available else 'Unavailable'}",
            f"html5validator: {'Available' if status.htmlvalidator_available else 'Unavailable'}",
            f"Torch: {'Available' if status.torch_available else 'Missing'}; CUDA: {'Yes' if status.cuda_available else 'No'}; MPS: {'Yes' if status.mps_available else 'No'}",
            f"Hugging Face hub: {'Available' if status.huggingface_available else 'Missing'}; Cache: {status.hf_cache_dir or 'Unknown'}",
            f"spaCy: {'Available' if status.spacy_available else 'Missing'}; Model: {status.spacy_model or 'None'}",
        ]
        self._env_status.setPlainText("\n".join(lines))

    def _open_hf_cache(self):
        st = getattr(self, "_last_env_status", None)
        if not st or not st.hf_cache_dir:
            return
        path = Path(st.hf_cache_dir)
        if not path.exists():
            QtWidgets.QMessageBox.information(self, "HF Cache", f"Path does not exist: {path}")
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path)))

    def _choose_project(self):
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, "Select project directory")
        if not directory:
            return
        self._set_project(Path(directory))

    def _open_selected_mru(self, item):
        self._set_project(Path(item.text()))

    def _set_project(self, root: Path):
        detected = discover_project(root)
        self._current_project = root
        add_mru(root)
        self._refresh_mru()
        if detected["exists"]:
            self._load_config(detected["config_path"])  # type: ignore[arg-type]
            self._tabs.setCurrentIndex(1)
            self._update_project_theme()
        else:
            QtWidgets.QMessageBox.information(
                self,
                "Project",
                f"No smilecms.yml found in {root}. Use Init to create one.",
            )

    def _init_project_dialog(self):
        target = QtWidgets.QFileDialog.getExistingDirectory(self, "Create or choose folder")
        if not target:
            return
        # Create minimal project structure by calling CLI init via service? For now, write a default config.
        root = Path(target)
        cfg_path = root / "smilecms.yml"
        if cfg_path.exists():
            QtWidgets.QMessageBox.information(self, "Init", "Config already exists here.")
        else:
            text = (
                "project_name: New SmileCMS Project\n"
                "content_dir: content\n"
                "article_media_dir: content/media\n"
                "media_dir: media\n"
                "output_dir: site\n"
                "templates_dir: web\n"
                "site_theme: \n"
                "cache_dir: .cache\n"
                "media_processing:\n"
                "  source_dir: content/media\n"
                "  output_dir: media/derived\n"
                "gallery:\n"
                "  enabled: true\n"
                "  source_dir: media/image_gallery_raw\n"
                "  metadata_filename: meta.yml\n"
                "music:\n"
                "  enabled: true\n"
                "  source_dir: media/music_collection\n"
                "  metadata_filename: meta.yml\n"
            )
            cfg_path.write_text(text, encoding="utf-8")
        add_mru(root)
        self._set_project(root)

    # ------------- Config Tab -------------
    def _init_config_tab(self):
        w = QtWidgets.QWidget()
        vlayout = QtWidgets.QVBoxLayout(w)

        self._config_path_label = QtWidgets.QLabel("Config: -")
        vlayout.addWidget(self._config_path_label)

        self._config_tabs = QtWidgets.QTabWidget()
        vlayout.addWidget(self._config_tabs, 1)

        # YAML editor tab
        yaml_tab = QtWidgets.QWidget()
        yv = QtWidgets.QVBoxLayout(yaml_tab)
        self._yaml_edit = QtWidgets.QPlainTextEdit()
        self._yaml_edit.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        yv.addWidget(self._yaml_edit, 1)
        ybtns = QtWidgets.QHBoxLayout()
        y_load = QtWidgets.QPushButton("Reload")
        y_load.clicked.connect(self._reload_config)
        y_diff = QtWidgets.QPushButton("Preview Changes")
        y_diff.clicked.connect(self._preview_diff)
        y_save = QtWidgets.QPushButton("Save (.bak)")
        y_save.clicked.connect(self._save_config)
        ybtns.addWidget(y_load)
        ybtns.addWidget(y_diff)
        ybtns.addWidget(y_save)
        ybtns.addStretch(1)
        yv.addLayout(ybtns)
        self._config_tabs.addTab(yaml_tab, "YAML")

        # Form editor tab
        form_tab = QtWidgets.QScrollArea()
        form_tab.setWidgetResizable(True)
        form_container = QtWidgets.QWidget()
        fv = QtWidgets.QVBoxLayout(form_container)

        # Project settings
        proj_box = QtWidgets.QGroupBox("Project")
        proj = QtWidgets.QFormLayout(proj_box)
        self._f_project_name = QtWidgets.QLineEdit()
        proj.addRow("Project name", self._f_project_name)
        fv.addWidget(proj_box)

        # Paths
        paths_box = QtWidgets.QGroupBox("Paths")
        paths = QtWidgets.QFormLayout(paths_box)
        self._f_content_dir = QtWidgets.QLineEdit()
        self._f_article_media_dir = QtWidgets.QLineEdit()
        self._f_media_dir = QtWidgets.QLineEdit()
        self._f_output_dir = QtWidgets.QLineEdit()
        self._f_templates_dir = QtWidgets.QLineEdit()
        self._f_site_theme = QtWidgets.QLineEdit()
        self._f_cache_dir = QtWidgets.QLineEdit()
        self._f_themes_dir = QtWidgets.QLineEdit()
        self._f_theme_name = QtWidgets.QLineEdit()
        paths.addRow("content_dir", self._f_content_dir)
        paths.addRow("article_media_dir", self._f_article_media_dir)
        paths.addRow("media_dir", self._f_media_dir)
        paths.addRow("output_dir", self._f_output_dir)
        paths.addRow("templates_dir", self._f_templates_dir)
        paths.addRow("site_theme", self._f_site_theme)
        paths.addRow("cache_dir", self._f_cache_dir)
        paths.addRow("themes_dir", self._f_themes_dir)
        paths.addRow("theme_name", self._f_theme_name)
        fv.addWidget(paths_box)

        # Media processing
        mp_box = QtWidgets.QGroupBox("Media processing")
        mp = QtWidgets.QFormLayout(mp_box)
        self._f_mp_source_dir = QtWidgets.QLineEdit()
        self._f_mp_output_dir = QtWidgets.QLineEdit()
        mp.addRow("media_processing.source_dir", self._f_mp_source_dir)
        mp.addRow("media_processing.output_dir", self._f_mp_output_dir)
        fv.addWidget(mp_box)

        # Gallery
        gal_box = QtWidgets.QGroupBox("Gallery")
        gal = QtWidgets.QFormLayout(gal_box)
        self._f_gal_enabled = QtWidgets.QCheckBox()
        self._f_gal_source_dir = QtWidgets.QLineEdit()
        self._f_gal_metadata_filename = QtWidgets.QLineEdit()
        gal.addRow("enabled", self._f_gal_enabled)
        gal.addRow("source_dir", self._f_gal_source_dir)
        gal.addRow("metadata_filename", self._f_gal_metadata_filename)
        fv.addWidget(gal_box)

        # Music
        mus_box = QtWidgets.QGroupBox("Music")
        mus = QtWidgets.QFormLayout(mus_box)
        self._f_mus_enabled = QtWidgets.QCheckBox()
        self._f_mus_source_dir = QtWidgets.QLineEdit()
        self._f_mus_metadata_filename = QtWidgets.QLineEdit()
        mus.addRow("enabled", self._f_mus_enabled)
        mus.addRow("source_dir", self._f_mus_source_dir)
        mus.addRow("metadata_filename", self._f_mus_metadata_filename)
        fv.addWidget(mus_box)

        # Feeds
        feed_box = QtWidgets.QGroupBox("Feeds")
        feed = QtWidgets.QFormLayout(feed_box)
        self._f_feed_enabled = QtWidgets.QCheckBox()
        self._f_feed_limit = QtWidgets.QSpinBox()
        self._f_feed_limit.setRange(1, 500)
        self._f_feed_base_url = QtWidgets.QLineEdit()
        self._f_feed_site_config_path = QtWidgets.QLineEdit()
        self._f_feed_output_subdir = QtWidgets.QLineEdit()
        feed.addRow("enabled", self._f_feed_enabled)
        feed.addRow("limit", self._f_feed_limit)
        feed.addRow("base_url", self._f_feed_base_url)
        feed.addRow("site_config_path", self._f_feed_site_config_path)
        feed.addRow("output_subdir", self._f_feed_output_subdir)
        fv.addWidget(feed_box)

        fbtns = QtWidgets.QHBoxLayout()
        f_apply = QtWidgets.QPushButton("Apply to YAML editor")
        f_apply.clicked.connect(self._apply_form_to_yaml)
        f_save = QtWidgets.QPushButton("Save (.bak) from form")
        f_save.clicked.connect(self._save_form_config)
        fbtns.addWidget(f_apply)
        fbtns.addWidget(f_save)
        fbtns.addStretch(1)
        fv.addLayout(fbtns)

        # Theme tools
        theme_box = QtWidgets.QGroupBox("Theme tools")
        th = QtWidgets.QVBoxLayout(theme_box)
        self._theme_status_label = QtWidgets.QLabel("Theme status: unknown")
        th.addWidget(self._theme_status_label)
        # Installed themes dropdown
        drop_row = QtWidgets.QHBoxLayout()
        self._installed_theme_combo = QtWidgets.QComboBox()
        self._apply_installed_theme_btn = QtWidgets.QPushButton("Use selected theme")
        self._apply_installed_theme_btn.clicked.connect(self._apply_installed_theme)
        drop_row.addWidget(QtWidgets.QLabel("Installed themes:"))
        drop_row.addWidget(self._installed_theme_combo)
        drop_row.addWidget(self._apply_installed_theme_btn)
        drop_row.addStretch(1)
        th.addLayout(drop_row)

        theme_btns = QtWidgets.QHBoxLayout()
        self._install_theme_btn = QtWidgets.QPushButton("Install default theme…")
        self._install_theme_btn.clicked.connect(self._install_theme_dialog)
        self._open_templates_btn = QtWidgets.QPushButton("Open templates folder")
        self._open_templates_btn.clicked.connect(self._open_templates_dir)
        theme_btns.addWidget(self._install_theme_btn)
        theme_btns.addWidget(self._open_templates_btn)
        theme_btns.addStretch(1)
        th.addLayout(theme_btns)
        fv.addWidget(theme_box)

        fv.addStretch(1)
        form_tab.setWidget(form_container)
        self._config_tabs.addTab(form_tab, "Form")

        self._tabs.addTab(w, "Configure")

    def _load_config(self, cfg_path: Path):
        cfg, path, text = load_config_with_text(cfg_path)
        self._current_config = cfg
        self._current_config_path = path
        self._current_config_text = text
        self._config_path_label.setText(f"Config: {path}")
        self._yaml_edit.setPlainText(text)
        self._populate_config_form(cfg)
        self._update_theme_status(cfg)
        self._update_project_theme()
        
    def _update_project_theme(self):
        if not self._current_config_path:
            self._project_theme_status.setText("")
            return
        cfg = load_config(self._current_config_path)
        resolved = cfg.resolved_templates_dir
        parts = []
        parts.append(f"templates_dir: {cfg.templates_dir}")
        parts.append(f"site_theme: {cfg.site_theme or '(not set)'}")
        parts.append(f"resolved theme path: {resolved} ({'exists' if resolved.exists() else 'missing'})")
        self._project_theme_status.setText("Theme • " + "; ".join(parts))

    def _reload_config(self):
        if self._current_config_path:
            self._load_config(self._current_config_path)

    def _preview_diff(self):
        after = self._yaml_edit.toPlainText()
        diff = diff_yaml(self._current_config_text, after)
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("YAML Diff")
        layout = QtWidgets.QVBoxLayout(dlg)
        view = QtWidgets.QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText(diff or "(no changes)")
        layout.addWidget(view)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)
        dlg.resize(800, 600)
        dlg.exec()

    def _save_config(self):
        if not self._current_config_path:
            return
        after_text = self._yaml_edit.toPlainText()
        # Parse to model to validate
        try:
            import yaml as _yaml

            data = _yaml.safe_load(after_text) or {}
            cfg = Config(**data)
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "Save", f"Invalid YAML or config: {exc}")
            return
        diff = diff_yaml(self._current_config_text, after_text)
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Save Config",
            "This will overwrite smilecms.yml and create a .bak. Proceed?\n\n"
            + (diff or "(no changes)"),
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        res = save_config(cfg, self._current_config_path, backup=True)
        self._current_config = cfg
        self._current_config_text = after_text
        self._config_path_label.setText(f"Config: {res['saved_path']}")
        QtWidgets.QMessageBox.information(self, "Save", "Configuration saved.")
        self._update_theme_status(cfg)

    def _populate_config_form(self, cfg: Config):
        self._f_project_name.setText(cfg.project_name)
        self._f_content_dir.setText(str(cfg.content_dir))
        self._f_article_media_dir.setText(str(cfg.article_media_dir))
        self._f_media_dir.setText(str(cfg.media_dir))
        self._f_output_dir.setText(str(cfg.output_dir))
        self._f_templates_dir.setText(str(cfg.templates_dir))
        self._f_site_theme.setText(str(cfg.site_theme or ""))
        self._f_cache_dir.setText(str(cfg.cache_dir))
        self._f_themes_dir.setText(str(cfg.themes_dir or ""))
        self._f_theme_name.setText(str(cfg.theme_name))
        self._f_mp_source_dir.setText(str(cfg.media_processing.source_dir))
        self._f_mp_output_dir.setText(str(cfg.media_processing.output_dir))
        self._f_gal_enabled.setChecked(bool(cfg.gallery.enabled))
        self._f_gal_source_dir.setText(str(cfg.gallery.source_dir))
        self._f_gal_metadata_filename.setText(str(cfg.gallery.metadata_filename))
        self._f_mus_enabled.setChecked(bool(cfg.music.enabled))
        self._f_mus_source_dir.setText(str(cfg.music.source_dir))
        self._f_mus_metadata_filename.setText(str(cfg.music.metadata_filename))
        self._f_feed_enabled.setChecked(bool(cfg.feeds.enabled))
        self._f_feed_limit.setValue(int(cfg.feeds.limit))
        self._f_feed_base_url.setText(str(cfg.feeds.base_url or ""))
        self._f_feed_site_config_path.setText(str(cfg.feeds.site_config_path or ""))
        self._f_feed_output_subdir.setText(str(cfg.feeds.output_subdir or ""))

    def _collect_form_data(self) -> Config:
        data = {
            "project_name": self._f_project_name.text(),
            "content_dir": self._f_content_dir.text(),
            "article_media_dir": self._f_article_media_dir.text(),
            "media_dir": self._f_media_dir.text(),
            "output_dir": self._f_output_dir.text(),
            "templates_dir": self._f_templates_dir.text(),
            "site_theme": self._f_site_theme.text() or None,
            "cache_dir": self._f_cache_dir.text(),
            "themes_dir": self._f_themes_dir.text() or None,
            "theme_name": self._f_theme_name.text() or "default",
            "media_processing": {
                "source_dir": self._f_mp_source_dir.text(),
                "output_dir": self._f_mp_output_dir.text(),
            },
            "gallery": {
                "enabled": self._f_gal_enabled.isChecked(),
                "source_dir": self._f_gal_source_dir.text(),
                "metadata_filename": self._f_gal_metadata_filename.text(),
            },
            "music": {
                "enabled": self._f_mus_enabled.isChecked(),
                "source_dir": self._f_mus_source_dir.text(),
                "metadata_filename": self._f_mus_metadata_filename.text(),
            },
            "feeds": {
                "enabled": self._f_feed_enabled.isChecked(),
                "limit": int(self._f_feed_limit.value()),
                "base_url": self._f_feed_base_url.text() or None,
                "site_config_path": self._f_feed_site_config_path.text() or None,
                "output_subdir": self._f_feed_output_subdir.text() or None,
            },
        }
        return Config(**data)

    def _apply_form_to_yaml(self):
        try:
            cfg = self._collect_form_data()
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "Config", f"Invalid values: {exc}")
            return
        from ..gui_service import render_config_yaml

        text = render_config_yaml(cfg)
        self._yaml_edit.setPlainText(text)

    def _save_form_config(self):
        if not self._current_config_path:
            return
        try:
            cfg = self._collect_form_data()
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "Config", f"Invalid values: {exc}")
            return
        from ..gui_service import render_config_yaml, save_config, diff_yaml

        after = render_config_yaml(cfg)
        diff = diff_yaml(self._current_config_text, after)
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Save Config (Form)",
            "This will overwrite smilecms.yml and create a .bak. Proceed?\n\n"
            + (diff or "(no changes)"),
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        res = save_config(cfg, self._current_config_path, backup=True)
        self._current_config = cfg
        self._current_config_text = after
        self._yaml_edit.setPlainText(after)
        self._config_path_label.setText(f"Config: {res['saved_path']}")
        QtWidgets.QMessageBox.information(self, "Save", "Configuration saved.")
        self._update_theme_status(cfg)

    def _update_theme_status(self, cfg: Config):
        try:
            templates_dir = Path(cfg.templates_dir)
            resolved = cfg.resolved_templates_dir
            status = []
            status.append(f"templates_dir: {'exists' if templates_dir.exists() else 'missing'} ({templates_dir})")
            if cfg.site_theme:
                status.append(f"site_theme: {cfg.site_theme}")
                status.append(
                    f"theme folder: {'exists' if resolved.exists() else 'missing'} ({resolved})"
                )
            else:
                status.append("site_theme: not set (using templates_dir root)")
                status.append(f"theme folder: {'exists' if resolved.exists() else 'missing'} ({resolved})")
            self._theme_status_label.setText("; ".join(status))
            # Refresh installed themes dropdown
            from ..gui_service import list_installed_themes

            themes = list_installed_themes(cfg)
            self._installed_theme_combo.clear()
            self._installed_theme_combo.addItems(themes)
            if cfg.site_theme and cfg.site_theme in themes:
                self._installed_theme_combo.setCurrentText(cfg.site_theme)
        except Exception as exc:  # noqa: BLE001
            self._theme_status_label.setText(f"Theme status error: {exc}")

    def _install_theme_dialog(self):
        if not self._current_config_path:
            QtWidgets.QMessageBox.warning(self, "Theme", "Open a project first.")
            return
        from ..gui_service import list_stock_themes, install_stock_theme

        themes = list_stock_themes()
        if not themes:
            QtWidgets.QMessageBox.information(
                self,
                "Theme",
                "No stock themes found in the examples directory. Ensure you're running from the repository checkout.",
            )
            return
        names = sorted(themes.keys())
        name, ok = QtWidgets.QInputDialog.getItem(self, "Install theme", "Theme", names, 0, False)
        if not ok or not name:
            return
        dest = Path(load_config(self._current_config_path).templates_dir) / name
        overwrite = False
        if dest.exists():
            resp = QtWidgets.QMessageBox.warning(
                self,
                "Overwrite?",
                f"Theme folder already exists: {dest}\nOverwrite files?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if resp != QtWidgets.QMessageBox.Yes:
                return
            overwrite = True
        try:
            result = install_stock_theme(self._current_config_path, name, overwrite=overwrite)
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "Theme", f"Install failed: {exc}")
            return
        # Reload config and update form
        self._load_config(self._current_config_path)
        QtWidgets.QMessageBox.information(
            self,
            "Theme",
            f"Installed theme to: {result['installed_path']} and updated config.",
        )

    def _open_templates_dir(self):
        if not self._current_config_path:
            return
        cfg = load_config(self._current_config_path)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(cfg.templates_dir)))

    def _apply_installed_theme(self):
        if not self._current_config_path:
            return
        name = self._installed_theme_combo.currentText().strip()
        if not name:
            return
        from ..gui_service import set_site_theme

        try:
            cfg = set_site_theme(self._current_config_path, name)
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "Theme", f"Failed to set theme: {exc}")
            return
        # Update UI
        self._current_config = cfg
        self._current_config_text = render_config_yaml(cfg)
        self._yaml_edit.setPlainText(self._current_config_text)
        self._populate_config_form(cfg)
        self._update_theme_status(cfg)
        self._update_project_theme()

    # ------------- New Content Tab -------------
    def _init_new_content_tab(self):
        w = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(w)

        self._kind_combo = QtWidgets.QComboBox()
        self._kind_combo.addItems(["post", "gallery", "track"])
        self._slug_edit = QtWidgets.QLineEdit()
        self._title_edit = QtWidgets.QLineEdit()
        self._force_new_chk = QtWidgets.QCheckBox("Force overwrite existing files")
        create_btn = QtWidgets.QPushButton("Create")
        create_btn.clicked.connect(self._create_content)

        layout.addRow("Kind", self._kind_combo)
        layout.addRow("Slug", self._slug_edit)
        layout.addRow("Title", self._title_edit)
        layout.addRow(self._force_new_chk)
        layout.addRow(create_btn)

        self._new_content_output = QtWidgets.QPlainTextEdit()
        self._new_content_output.setReadOnly(True)
        layout.addRow(self._new_content_output)

        self._tabs.addTab(w, "New Content")

    def _create_content(self):
        if not self._current_config_path:
            QtWidgets.QMessageBox.warning(self, "New Content", "Open a project first.")
            return
        kind = self._kind_combo.currentText()
        slug = self._slug_edit.text().strip()
        title = self._title_edit.text().strip() or None
        force = self._force_new_chk.isChecked()
        try:
            result = scaffold(kind, slug, title=title, force=force, config_path=self._current_config_path)
            lines = ["Created/Updated:"]
            for p in result.created:
                lines.append(f"- {p} (new)")
            for p in result.updated:
                lines.append(f"- {p} (updated)")
            if result.notes:
                lines.append("\nNext steps:")
                for note in result.notes:
                    lines.append(f"- {note}")
            self._new_content_output.setPlainText("\n".join(lines))
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "New Content", str(exc))

    # ------------- Build Tab -------------
    def _init_build_tab(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        opts = QtWidgets.QHBoxLayout()
        self._force_build = QtWidgets.QCheckBox("Force rebuild (clears outputs)")
        self._refresh_gallery = QtWidgets.QCheckBox("Refresh gallery (overwrite sidecars)")
        opts.addWidget(self._force_build)
        opts.addWidget(self._refresh_gallery)
        opts.addStretch(1)
        v.addLayout(opts)

        # Granular progress bars
        bars = QtWidgets.QGridLayout()
        bars.addWidget(QtWidgets.QLabel("Derivatives"), 0, 0)
        self._bar_deriv = QtWidgets.QProgressBar()
        self._bar_deriv.setRange(0, 1)
        bars.addWidget(self._bar_deriv, 0, 1)
        bars.addWidget(QtWidgets.QLabel("Assets"), 1, 0)
        self._bar_assets = QtWidgets.QProgressBar()
        self._bar_assets.setRange(0, 1)
        bars.addWidget(self._bar_assets, 1, 1)
        v.addLayout(bars)

        self._build_output = QtWidgets.QPlainTextEdit()
        self._build_output.setReadOnly(True)
        v.addWidget(self._build_output, 1)

        run_btn = QtWidgets.QPushButton("Build")
        run_btn.clicked.connect(self._run_build)
        v.addWidget(run_btn)

        # Clean section
        clean_box = QtWidgets.QGroupBox("Clean generated artifacts")
        ch = QtWidgets.QHBoxLayout(clean_box)
        self._clean_cache = QtWidgets.QCheckBox("Include cache directory")
        clean_btn = QtWidgets.QPushButton("Clean…")
        clean_btn.clicked.connect(self._run_clean)
        ch.addWidget(self._clean_cache)
        ch.addWidget(clean_btn)
        ch.addStretch(1)
        v.addWidget(clean_box)

        self._tabs.addTab(w, "Build")

    def _run_build(self):
        if not self._current_config_path:
            QtWidgets.QMessageBox.warning(self, "Build", "Open a project first.")
            return
        if self._refresh_gallery.isChecked():
            confirm = QtWidgets.QMessageBox.warning(
                self,
                "Refresh Gallery",
                (
                    "This will overwrite gallery sidecars and may discard manual edits.\n"
                    "Are you sure you want to continue?"
                ),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if confirm != QtWidgets.QMessageBox.Yes:
                return

        cfg = load_config(self._current_config_path)
        opts = BuildOptions(force=self._force_build.isChecked(), refresh_gallery=self._refresh_gallery.isChecked())
        self._build_output.clear()
        self._build_progress.setRange(0, 0)

        def log(msg: str):
            self._build_output.appendPlainText(msg)

        # Reset counters
        self._deriv_done = 0
        self._deriv_total = 0
        self._asset_done = 0
        self._asset_total = 0

        def on_progress(step: str, inc: int, total: int):
            if step == "Derivatives":
                if self._deriv_total != total:
                    self._deriv_total = total
                    self._bar_deriv.setRange(0, max(total, 1))
                self._deriv_done = min(self._deriv_done + inc, self._deriv_total or 1)
                self._bar_deriv.setValue(self._deriv_done)
            elif step == "Assets":
                if self._asset_total != total:
                    self._asset_total = total
                    self._bar_assets.setRange(0, max(total, 1))
                self._asset_done = min(self._asset_done + inc, self._asset_total or 1)
                self._bar_assets.setValue(self._asset_done)

        from ..gui_service import build as svc_build

        self._run_in_thread(
            svc_build,
            cfg,
            config_file_path=self._current_config_path,
            options=opts,
            progress_cb=on_progress,
            log_cb=log,
        )

    def _run_clean(self):
        if not self._current_config_path:
            QtWidgets.QMessageBox.warning(self, "Clean", "Open a project first.")
            return
        cfg = load_config(self._current_config_path)
        include_cache = self._clean_cache.isChecked()
        # Show guardrail confirmation
        paths = [
            ("site output", str(cfg.output_dir)),
            ("media derivatives", str(cfg.media_processing.output_dir)),
        ]
        if include_cache:
            paths.append(("cache", str(cfg.cache_dir)))
        text = "This will permanently delete the following directories:\n\n"
        text += "\n".join(f"- {label}: {p}" for label, p in paths)
        text += "\n\nType CONFIRM to proceed."
        input_text, ok = QtWidgets.QInputDialog.getText(self, "Confirm Clean", text)
        if not ok or input_text.strip().upper() != "CONFIRM":
            return
        from ..gui_service import clean as svc_clean

        result = svc_clean(cfg, include_cache=include_cache)
        lines = ["Clean complete:"]
        for label, path in result["removed"]:
            lines.append(f"- Removed {label}: {path}")
        for label, path in result["skipped"]:
            lines.append(f"- Skipped {label}: {path} (not found)")
        QtWidgets.QMessageBox.information(self, "Clean", "\n".join(lines))

    # ------------- Test Tab -------------
    def _init_test_tab(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        toggles = QtWidgets.QHBoxLayout()
        self._test_links = QtWidgets.QCheckBox("Link/Asset scan")
        self._test_links.setChecked(True)
        self._test_html = QtWidgets.QCheckBox("HTML validation")
        self._test_html.setChecked(True)
        self._test_js = QtWidgets.QCheckBox("JS validation")
        self._test_js.setChecked(True)
        toggles.addWidget(self._test_links)
        toggles.addWidget(self._test_html)
        toggles.addWidget(self._test_js)
        toggles.addStretch(1)
        v.addLayout(toggles)

        self._test_output = QtWidgets.QPlainTextEdit()
        self._test_output.setReadOnly(True)
        v.addWidget(self._test_output, 1)

        btns = QtWidgets.QHBoxLayout()
        run_btn = QtWidgets.QPushButton("Run Tests")
        run_btn.clicked.connect(self._run_tests)
        export_btn = QtWidgets.QPushButton("Export Text Report…")
        export_btn.clicked.connect(self._export_test_report)
        btns.addWidget(run_btn)
        btns.addWidget(export_btn)
        btns.addStretch(1)
        v.addLayout(btns)

        self._tabs.addTab(w, "Test")

        self._last_test_report: Optional[VerificationReport] = None
        self._last_html_report: Optional[HtmlValidationReport] = None
        self._last_js_report: Optional[JsValidationReport] = None

    def _run_tests(self):
        if not self._current_config_path:
            QtWidgets.QMessageBox.warning(self, "Tests", "Open a project first.")
            return
        cfg = load_config(self._current_config_path)
        out_lines = []
        if self._test_links.isChecked():
            rep = verify_links(cfg)
            self._last_test_report = rep
            out_lines.append(f"Verification: scanned {rep.scanned_files} HTML files; issues: {len(rep.issues)}")
            for issue in rep.issues[:200]:
                out_lines.append(f"- [{issue.kind}] {issue.source} -> {issue.target} :: {issue.message}")
        if self._test_html.isChecked():
            html_rep = validate_html_safe(cfg)
            if isinstance(html_rep, tuple):
                out_lines.append(f"HTML validation skipped: {html_rep[1]}")
            else:
                self._last_html_report = html_rep
                out_lines.append(
                    f"HTML: files {html_rep.scanned_files} errors {html_rep.error_count} warnings {html_rep.warning_count}"
                )
        if self._test_js.isChecked():
            js_rep = validate_js_safe(cfg)
            if isinstance(js_rep, tuple):
                out_lines.append(f"JS validation skipped: {js_rep[1]}")
            else:
                self._last_js_report = js_rep
                out_lines.append(
                    f"JS: files {js_rep.scanned_files} errors {js_rep.error_count} warnings {js_rep.warning_count}"
                )
        self._test_output.setPlainText("\n".join(out_lines))

    def _export_test_report(self):
        if not (self._last_test_report and self._current_config_path):
            return
        target, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save report", "verification.txt")
        if not target:
            return
        cfg = load_config(self._current_config_path)
        text = render_verification_text(
            self._last_test_report,
            Path(cfg.output_dir),
            self._last_html_report,
            self._last_js_report,
        )
        Path(target).write_text(text, encoding="utf-8")
        QtWidgets.QMessageBox.information(self, "Export", "Report written.")

    # ------------- Preview Tab -------------
    def _init_preview_tab(self):
        w = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(w)
        self._host_edit = QtWidgets.QLineEdit("127.0.0.1")
        self._port_edit = QtWidgets.QLineEdit("8000")
        form.addRow("Host", self._host_edit)
        form.addRow("Port", self._port_edit)

        btns = QtWidgets.QHBoxLayout()
        self._start_preview_btn = QtWidgets.QPushButton("Start")
        self._stop_preview_btn = QtWidgets.QPushButton("Stop")
        self._open_browser_btn = QtWidgets.QPushButton("Open in Browser")
        self._start_preview_btn.clicked.connect(self._start_preview)
        self._stop_preview_btn.clicked.connect(self._stop_preview)
        self._open_browser_btn.clicked.connect(self._open_preview_in_browser)
        btns.addWidget(self._start_preview_btn)
        btns.addWidget(self._stop_preview_btn)
        btns.addWidget(self._open_browser_btn)
        form.addRow(btns)

        self._preview_status = QtWidgets.QLabel("Idle")
        form.addRow("Status", self._preview_status)

        self._tabs.addTab(w, "Preview")

    def _start_preview(self):
        if not self._current_config_path:
            QtWidgets.QMessageBox.warning(self, "Preview", "Open a project first.")
            return
        cfg = load_config(self._current_config_path)
        host = self._host_edit.text().strip() or "127.0.0.1"
        try:
            port = int(self._port_edit.text().strip() or "8000")
        except ValueError:
            port = 8000
        try:
            handle = start_preview_server(cfg, host=host, port=port)
            self._preview_handle = handle
            url_host = "127.0.0.1" if handle.host in {"0.0.0.0", ""} else handle.host
            self._preview_status.setText(f"Serving {cfg.output_dir} at http://{url_host}:{handle.port}/")
            self._port_edit.setText(str(handle.port))
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "Preview", f"Failed to start server: {exc}")

    def _stop_preview(self):
        try:
            stop_preview_server(self._preview_handle)
        except Exception:
            pass
        self._preview_handle = None
        self._preview_status.setText("Idle")

    def _open_preview_in_browser(self):
        if not self._preview_handle:
            return
        host = "127.0.0.1" if self._preview_handle.host in {"0.0.0.0", ""} else self._preview_handle.host
        url = f"http://{host}:{self._preview_handle.port}/"
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))

    # ------------- Audit Tab -------------
    def _init_audit_tab(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        self._audit_output = QtWidgets.QPlainTextEdit()
        self._audit_output.setReadOnly(True)
        v.addWidget(self._audit_output, 1)
        btns = QtWidgets.QHBoxLayout()
        run_btn = QtWidgets.QPushButton("Run Media Audit")
        run_btn.clicked.connect(self._run_audit)
        export_btn = QtWidgets.QPushButton("Export JSON…")
        export_btn.clicked.connect(self._export_audit_json)
        btns.addWidget(run_btn)
        btns.addWidget(export_btn)
        btns.addStretch(1)
        v.addLayout(btns)
        self._tabs.addTab(w, "Audit")

        self._last_audit = None

    def _run_audit(self):
        if not self._current_config_path:
            QtWidgets.QMessageBox.warning(self, "Audit", "Open a project first.")
            return
        cfg = load_config(self._current_config_path)
        docs = load_documents(cfg)
        result = audit_media(docs, cfg)
        self._last_audit = result
        lines = [
            f"Assets: {result.total_assets}; references: {result.total_references}; valid: {result.valid_references}",
            f"Missing: {len(result.missing_references)}; OOB: {len(result.out_of_bounds_references)}; Orphan: {len(result.orphan_files)}; Stray: {len(result.stray_files)}",
        ]
        self._audit_output.setPlainText("\n".join(lines))

    def _export_audit_json(self):
        if not self._last_audit:
            return
        target, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save JSON", "media_audit.json")
        if not target:
            return
        payload = audit_media_json_payload(self._last_audit)
        Path(target).write_text(
            __import__("json").dumps(payload, indent=2), encoding="utf-8"
        )
        QtWidgets.QMessageBox.information(self, "Export", "JSON written.")

    # ------------- Thread helper -------------
    def _run_in_thread(self, fn, *args, **kwargs):
        self._thread = QtCore.QThread(self)
        self._worker = Worker(fn, *args, **kwargs)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._on_worker_done)
        self._worker.error.connect(self._on_worker_error)
        self._worker.log.connect(lambda m: None)
        self._thread.start()

    @QtCore.Slot(object)
    def _on_worker_done(self, result):
        if isinstance(result, BuildResult):
            self._build_output.appendPlainText("Build complete.")
            # Ensure bars show completion
            self._bar_deriv.setValue(self._bar_deriv.maximum())
            self._bar_assets.setValue(self._bar_assets.maximum())
        self._thread.quit()
        self._thread.wait()

    @QtCore.Slot(str)
    def _on_worker_error(self, message: str):
        QtWidgets.QMessageBox.critical(self, "Error", message)
        try:
            self._thread.quit()
            self._thread.wait()
        except Exception:
            pass


def main():
    app = QtWidgets.QApplication(sys.argv)
    # Basic dark theme
    app.setStyle("Fusion")
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor(53, 53, 53))
    palette.setColor(QtGui.QPalette.WindowText, QtCore.Qt.white)
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor(35, 35, 35))
    palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(53, 53, 53))
    palette.setColor(QtGui.QPalette.ToolTipBase, QtCore.Qt.white)
    palette.setColor(QtGui.QPalette.ToolTipText, QtCore.Qt.white)
    palette.setColor(QtGui.QPalette.Text, QtCore.Qt.white)
    palette.setColor(QtGui.QPalette.Button, QtGui.QColor(53, 53, 53))
    palette.setColor(QtGui.QPalette.ButtonText, QtCore.Qt.white)
    palette.setColor(QtGui.QPalette.BrightText, QtCore.Qt.red)
    palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(142, 45, 197).lighter())
    palette.setColor(QtGui.QPalette.HighlightedText, QtCore.Qt.black)
    app.setPalette(palette)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
