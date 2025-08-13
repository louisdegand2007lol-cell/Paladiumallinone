#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Paladium Desktop — Fixed Windows build
- PyQt6 app (no qdarktheme dependency)
- Tabs: Market (sorting/filtering/CSV + charts), Players, Factions, Status/Events, Settings
- Robust for PyInstaller (onedir + qt plugin path hints)
"""
import sys, os, json, threading, queue, csv
from typing import Any, Dict, List, Optional, Tuple

# --- Qt plugin env hint for PyInstaller ---
if getattr(sys, "frozen", False):
    base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    os.environ.setdefault("QT_PLUGIN_PATH", os.path.join(base, "PyQt6", "Qt6", "plugins"))
    os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", os.path.join(base, "PyQt6", "Qt6", "plugins", "platforms"))

import requests

from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QVariant, QSortFilterProxyModel, QRegularExpression, QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableView, QHeaderView, QFileDialog, QFormLayout, QSpinBox,
    QGroupBox, QMessageBox, QComboBox, QCheckBox
)
from PyQt6.QtCharts import QChart, QChartView, QBarSeries, QBarSet, QBarCategoryAxis, QValueAxis, QScatterSeries

APP_NAME = "Paladium Desktop"
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".paladium_desktop")
os.makedirs(CONFIG_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
DEFAULT_CONFIG = {
    "api_base": "https://api.paladium.games",
    "api_key": "a6123ab4-4ca9-42c1-b1f0-f49d16906aa1",
    "auth_scheme": "Bearer",  # Bearer | Plain | X-API-Key | Query
    "auth_header": "X-API-Key",
    "timeout": 15,
    "page_size": 50
}

def load_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_FILE):
        try:
            return json.loads(open(CONFIG_FILE, "r", encoding="utf-8").read())
        except Exception:
            pass
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(DEFAULT_CONFIG, indent=2))
    return DEFAULT_CONFIG.copy()

def save_config(cfg: Dict[str, Any]) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(cfg, indent=2))

class ApiClient:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg

    def _headers(self) -> Dict[str, str]:
        key = self.cfg.get("api_key") or ""
        scheme = self.cfg.get("auth_scheme", "Bearer")
        headers = {"Accept": "application/json"}
        if scheme == "Bearer":
            headers["Authorization"] = f"Bearer {key}"
        elif scheme == "Plain":
            headers["Authorization"] = key
        elif scheme == "X-API-Key":
            headers[self.cfg.get("auth_header","X-API-Key")] = key
        return headers

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        base = self.cfg.get("api_base", "").rstrip("/")
        url = f"{base}{path}"
        headers = self._headers()
        params = dict(params or {})
        if self.cfg.get("auth_scheme") == "Query":
            params["apikey"] = self.cfg.get("api_key", "")
        r = requests.get(url, headers=headers, params=params, timeout=self.cfg.get("timeout", 15))
        r.raise_for_status()
        try:
            return r.json()
        except Exception:
            return r.text

    # API methods (best-effort)
    def market_items(self, page: int = 1, size: int = 100, search: str = "", sort: str = "") -> Any:
        params = {"page": page, "size": size}
        if search: params["q"] = search
        if sort: params["sort"] = sort
        return self._get("/v1/paladium/shop/market/items", params)

    def player_profile(self, ident: str) -> Any:
        return self._get(f"/v1/players/{ident}")

    def faction_profile(self, fid: str) -> Any:
        return self._get(f"/v1/factions/{fid}")

    def server_status(self) -> Any:
        return self._get("/v1/status")

# --- Market model/UI ---
class MarketTableModel(QAbstractTableModel):
    COLUMNS = ["Item", "Category", "Price", "Quantity", "Seller", "Timestamp"]
    def __init__(self): super().__init__(); self.rows = []
    def rowCount(self, parent=QModelIndex()): return len(self.rows)
    def columnCount(self, parent=QModelIndex()): return len(self.COLUMNS)
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid(): return QVariant()
        row = self.rows[index.row()]; col = self.COLUMNS[index.column()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return str(row.get(col.lower(), ""))
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter) if col in ("Price","Quantity","Timestamp") else int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return QVariant()
    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole: return QVariant()
        return self.COLUMNS[section] if orientation == Qt.Orientation.Horizontal else str(section+1)
    def update(self, rows): self.beginResetModel(); self.rows = rows; self.endResetModel()

class MarketTab(QWidget):
    def __init__(self, api: ApiClient, cfg: Dict[str, Any]):
        super().__init__(); self.api=api; self.cfg=cfg; self.cur_page=1; self.page_size=cfg.get("page_size",50); self.raw_rows=[]
        v=QVBoxLayout(self); ctl=QHBoxLayout(); 
        self.search=QLineEdit(placeholderText="Rechercher un item…"); self.minp=QLineEdit(placeholderText="Prix min"); self.maxp=QLineEdit(placeholderText="Prix max")
        self.sort=QComboBox(); self.sort.addItems(["","price_asc","price_desc","quantity_desc"])
        self.refresh=QPushButton("Actualiser"); self.export=QPushButton("Exporter CSV")
        for w in (QLabel("🔎"), self.search, QLabel("Tri"), self.sort, self.minp, self.maxp, self.refresh, self.export): ctl.addWidget(w)
        v.addLayout(ctl)
        self.model=MarketTableModel(); self.proxy=QSortFilterProxyModel(self); self.proxy.setSourceModel(self.model); self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive); self.proxy.setFilterKeyColumn(-1)
        self.table=QTableView(); self.table.setModel(self.proxy); self.table.setSortingEnabled(True); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); v.addWidget(self.table,3)
        charts=QHBoxLayout(); self.chart_top=QChartView(); self.chart_avg=QChartView(); self.chart_disp=QChartView(); charts.addWidget(self.chart_top); charts.addWidget(self.chart_avg); charts.addWidget(self.chart_disp); v.addLayout(charts,2)
        pag=QHBoxLayout(); self.prev=QPushButton("◀"); self.page=QLabel("Page 1"); self.next=QPushButton("▶"); [pag.addWidget(x) for x in (self.prev,self.page,self.next)]; v.addLayout(pag)
        self.refresh.clicked.connect(self.reload); self.search.textChanged.connect(self.apply_filter); self.minp.textChanged.connect(self.apply_filter); self.maxp.textChanged.connect(self.apply_filter); self.sort.currentIndexChanged.connect(self.reload); self.prev.clicked.connect(self._prev); self.next.clicked.connect(self._next); self.export.clicked.connect(self.export_csv)
        QTimer.singleShot(200,self.reload)

    def export_csv(self):
        path,_=QFileDialog.getSaveFileName(self,"Exporter CSV","market.csv","CSV (*.csv)"); 
        if not path: return
        rows=[]; 
        for r in range(self.proxy.rowCount()):
            d={}
            for c,name in enumerate(MarketTableModel.COLUMNS): d[name]=self.proxy.data(self.proxy.index(r,c))
            rows.append(d)
        with open(path,"w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f, fieldnames=MarketTableModel.COLUMNS); w.writeheader(); w.writerows(rows)
        QMessageBox.information(self,"Export",f"{len(rows)} lignes exportées.")

    def _prev(self):
        if self.cur_page>1: self.cur_page-=1; self.reload()
    def _next(self):
        self.cur_page+=1; self.reload()

    def reload(self):
        self.page.setText(f"Chargement… (page {self.cur_page})")
        import threading
        def worker():
            try:
                payload=self.api.market_items(page=self.cur_page,size=self.page_size,search=self.search.text().strip(),sort=self.sort.currentText())
                items=payload.get("data") if isinstance(payload,dict) else payload
                if not isinstance(items,list): items=[]
                rows=[]
                for it in items:
                    rows.append({"item":it.get("item") or it.get("name") or "",
                                 "category":it.get("category") or "",
                                 "price":it.get("price") or it.get("unit_price") or 0,
                                 "quantity":it.get("quantity") or it.get("count") or 1,
                                 "seller":it.get("seller") or it.get("owner") or "",
                                 "timestamp":it.get("timestamp") or it.get("created_at") or ""})
                self.raw_rows=rows
                self.model.update(rows)
                self.apply_filter()
                self.page.setText(f"Page {self.cur_page}")
            except Exception as e:
                self.page.setText(f"Page {self.cur_page}")
                QMessageBox.critical(self,"Erreur API",str(e))
        threading.Thread(target=worker,daemon=True).start()

    def apply_filter(self):
        term=self.search.text(); self.proxy.setFilterRegularExpression(QRegularExpression(term))
        def price_ok(r):
            try: p=float(r.get("price",0))
            except Exception: return False
            mn=self.minp.text().strip(); mx=self.maxp.text().strip()
            if mn and p<float(mn): return False
            if mx and p>float(mx): return False
            return True
        filtered=[r for r in self.raw_rows if price_ok(r)]
        self.model.update(filtered)
        self._charts(filtered)

    def _charts(self, rows):
        # Top quantities
        qty={}; 
        for r in rows:
            try: qty[r["item"]]=qty.get(r["item"],0)+int(r.get("quantity",0))
            except: pass
        top=sorted(qty.items(), key=lambda x:x[1], reverse=True)[:20]
        s=QBarSeries(); bs=QBarSet("Quantité"); cats=[]
        for name,val in top: bs.append(float(val)); cats.append(name[:16])
        s.append(bs)
        c=QChart(); c.setTitle("Top 20 — quantité"); c.addSeries(s); ax=QBarCategoryAxis(); ax.append(cats); ay=QValueAxis(); ay.setLabelFormat("%d"); c.addAxis(ax, Qt.AlignmentFlag.AlignBottom); c.addAxis(ay, Qt.AlignmentFlag.AlignLeft); s.attachAxis(ax); s.attachAxis(ay); self.chart_top.setChart(c)
        # Avg/Median price for same set
        prices={}
        for r in rows:
            try: prices.setdefault(r["item"],[]).append(float(r.get("price",0)))
            except: pass
        def avg(lst): return sum(lst)/len(lst) if lst else 0.0
        def med(lst):
            if not lst: return 0.0
            srt=sorted(lst); n=len(srt); m=n//2
            return srt[m] if n%2 else (srt[m-1]+srt[m])/2.0
        s2=QBarSeries(); sa=QBarSet("Moyen"); sm=QBarSet("Médian"); cats2=[]
        for name,_ in top:
            lst=prices.get(name,[]); sa.append(avg(lst)); sm.append(med(lst)); cats2.append(name[:16])
        s2.append(sa); s2.append(sm)
        c2=QChart(); c2.setTitle("Prix moyen vs médian"); c2.addSeries(s2); ax2=QBarCategoryAxis(); ax2.append(cats2); ay2=QValueAxis(); c2.addAxis(ax2, Qt.AlignmentFlag.AlignBottom); c2.addAxis(ay2, Qt.AlignmentFlag.AlignLeft); s2.attachAxis(ax2); s2.attachAxis(ay2); self.chart_avg.setChart(c2)
        # Dispersion price vs qty by category (limited series)
        by_cat={}
        for r in rows:
            try:
                p=float(r.get("price",0)); q=float(r.get("quantity",0)); cat=r.get("category") or "N/A"
                by_cat.setdefault(cat,[]).append((p,q))
            except: pass
        c3=QChart(); c3.setTitle("Prix vs Quantité (par catégorie)"); ax3=QValueAxis(); ax3.setTitleText("Prix"); ay3=QValueAxis(); ay3.setTitleText("Quantité"); c3.addAxis(ax3, Qt.AlignmentFlag.AlignBottom); c3.addAxis(ay3, Qt.AlignmentFlag.AlignLeft)
        for cat,pts in list(by_cat.items())[:6]:
            sc=QScatterSeries(); sc.setName(cat)
            for p,q in pts[:200]: sc.append(p,q)
            c3.addSeries(sc); sc.attachAxis(ax3); sc.attachAxis(ay3)
        self.chart_disp.setChart(c3)

class PlayerTab(QWidget):
    def __init__(self, api: ApiClient):
        super().__init__(); self.api=api
        v=QVBoxLayout(self); row=QHBoxLayout(); self.q=QLineEdit(placeholderText="Pseudo ou UUID…"); self.btn=QPushButton("Rechercher"); row.addWidget(self.q); row.addWidget(self.btn); v.addLayout(row); self.out=QLabel(""); self.out.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); v.addWidget(self.out); self.btn.clicked.connect(self.search)
    def search(self):
        term=self.q.text().strip(); 
        if not term: return
        self.out.setText("Chargement…")
        import threading
        def worker():
            try: payload=self.api.player_profile(term); txt=json.dumps(payload,indent=2,ensure_ascii=False)
            except Exception as e: txt=f"Erreur: {e}"
            self.out.setText(txt)
        threading.Thread(target=worker,daemon=True).start()

class FactionTab(QWidget):
    def __init__(self, api: ApiClient):
        super().__init__(); self.api=api
        v=QVBoxLayout(self); row=QHBoxLayout(); self.q=QLineEdit(placeholderText="ID de faction…"); self.btn=QPushButton("Charger"); row.addWidget(self.q); row.addWidget(self.btn); v.addLayout(row); self.out=QLabel(""); self.out.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); v.addWidget(self.out); self.btn.clicked.connect(self.load)
    def load(self):
        fid=self.q.text().strip(); 
        if not fid: return
        self.out.setText("Chargement…")
        import threading
        def worker():
            try: payload=self.api.faction_profile(fid); txt=json.dumps(payload,indent=2,ensure_ascii=False)
            except Exception as e: txt=f"Erreur: {e}"
            self.out.setText(txt)
        threading.Thread(target=worker,daemon=True).start()

class StatusTab(QWidget):
    def __init__(self, api: ApiClient):
        super().__init__(); self.api=api
        v=QVBoxLayout(self); self.btn=QPushButton("Rafraîchir"); self.out=QLabel(""); self.out.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); v.addWidget(self.btn); v.addWidget(self.out); self.btn.clicked.connect(self.refresh)
    def refresh(self):
        self.out.setText("Chargement…")
        import threading
        def worker():
            try: payload=self.api.server_status(); txt=json.dumps(payload,indent=2,ensure_ascii=False)
            except Exception as e: txt=f"Erreur: {e}"
            self.out.setText(txt)
        threading.Thread(target=worker,daemon=True).start()

class SettingsTab(QWidget):
    def __init__(self, cfg: Dict[str, Any], api: ApiClient, on_change):
        super().__init__(); self.cfg=cfg; self.api=api; self.on_change=on_change
        form=QFormLayout(self)
        self.api_base=QLineEdit(cfg.get("api_base","")); self.api_key=QLineEdit(cfg.get("api_key",""))
        self.auth_sch=QComboBox(); self.auth_sch.addItems(["Bearer","Plain","X-API-Key","Query"]); self.auth_sch.setCurrentText(cfg.get("auth_scheme","Bearer"))
        self.auth_hdr=QLineEdit(cfg.get("auth_header","X-API-Key"))
        self.timeout=QSpinBox(); self.timeout.setRange(5,120); self.timeout.setValue(int(cfg.get("timeout",15)))
        self.page_size=QSpinBox(); self.page_size.setRange(10,500); self.page_size.setValue(int(cfg.get("page_size",50)))
        btn=QPushButton("Enregistrer")
        form.addRow("API base", self.api_base); form.addRow("API key", self.api_key); form.addRow("Auth scheme", self.auth_sch); form.addRow("Auth header", self.auth_hdr); form.addRow("Timeout (s)", self.timeout); form.addRow("Taille page", self.page_size); form.addRow(btn)
        btn.clicked.connect(self.save)
    def save(self):
        self.cfg["api_base"]=self.api_base.text().strip(); self.cfg["api_key"]=self.api_key.text().strip()
        self.cfg["auth_scheme"]=self.auth_sch.currentText(); self.cfg["auth_header"]=self.auth_hdr.text().strip()
        self.cfg["timeout"]=int(self.timeout.value()); self.cfg["page_size"]=int(self.page_size.value())
        save_config(self.cfg); QMessageBox.information(self,"Paramètres","Enregistré."); self.on_change()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle(APP_NAME); self.resize(1200,800)
        self.cfg=load_config(); self.api=ApiClient(self.cfg)
        tabs=QTabWidget(); tabs.addTab(MarketTab(self.api,self.cfg),"Market"); tabs.addTab(PlayerTab(self.api),"Joueurs"); tabs.addTab(FactionTab(self.api),"Factions"); tabs.addTab(StatusTab(self.api),"Serveurs/Events"); tabs.addTab(SettingsTab(self.cfg,self.api,self._on_change),"Paramètres"); self.setCentralWidget(tabs)
        act=QAction("Exporter Market CSV",self); act.triggered.connect(lambda: getattr(tabs.widget(0),"export_csv")()); self.menuBar().addAction(act)
    def _on_change(self): self.api=ApiClient(self.cfg)

def main():
    app=QApplication(sys.argv)
    w=MainWindow(); w.show()
    sys.exit(app.exec())

if __name__=="__main__":
    main()
