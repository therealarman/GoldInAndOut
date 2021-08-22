# general
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
from functools import partial
import seaborn as sns
import numpy as np
import pandas as pd
import datetime
import logging
import os
import shutil
import traceback
import cv2

# pyQT5
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread, QSize, QByteArray
from PyQt5.QtGui import QImage, QPixmap, QCursor, QMovie
from PyQt5.QtWidgets import (QLabel, QRadioButton, QCheckBox, QHBoxLayout, QPushButton, QWidget, QSizePolicy,
                             QFormLayout, QLineEdit,
                             QComboBox, QProgressBar, QToolButton, QVBoxLayout, QListWidgetItem)

# views
from views.image_viewer import QImageViewer
from views.logger import Logger

# utils
from globals import PALETTE_OPS, MAX_DIRS_PRUNE
from typings import Unit, Workflow, DataObj, OutputOptions, WorkflowObj
from typing import List, Tuple
from utils import Progress, create_color_pal, enum_to_unit, to_coord_list, pixels_conversion

# workflows
from workflows.clust import run_clust, draw_clust
from workflows.gold_rippler import run_rippler, draw_rippler
from workflows.nnd import run_nnd, draw_length
from workflows.nnd_clust import run_nnd_clust, draw_nnd_clust
from workflows.random_coords import gen_random_coordinates
from workflows.starfish import run_starfish, draw_starfish


class AnalysisWorker(QObject):
    finished = pyqtSignal(object)
    progress = pyqtSignal(int)
    
    def run(self, wf: WorkflowObj, vals: List[str], coords: List[Tuple[float, float]], rand_coords: List[Tuple[float, float]], alt_coords: List[Tuple[float, float]] = None, img_path: str = "", mask_path: str = ""):
        try:
            real_df1 = real_df2 = rand_df1 = rand_df2 = pd.DataFrame()
            
            if wf['type'] == Workflow.NND:
                real_df1, rand_df1 = run_nnd(real_coords=coords, rand_coords=rand_coords, )
            elif wf['type'] == Workflow.CLUST:
                real_df1, rand_df1, real_df2, rand_df2 = run_clust(
                    real_coords=coords, rand_coords=rand_coords, img_path=img_path, distance_threshold=vals[0], n_clusters=vals[1], pb=self.progress)
            elif wf['type'] == Workflow.NND_CLUST:
                real_df2, rand_df2, real_df1, rand_df1 = run_nnd_clust(real_coords=coords, rand_coords=rand_coords,  distance_threshold=vals[0],  n_clusters=vals[1], min_clust_size=vals[2])
            elif wf['type'] == Workflow.RIPPLER:
                real_df1, rand_df1 = run_rippler(real_coords=coords, alt_coords=alt_coords, rand_coords=rand_coords,
                                               img_path=img_path, mask_path=mask_path, max_steps=vals[0], step_size=vals[1])
            elif wf['type'] == Workflow.STARFISH:
                real_df1, rand_df1 = run_starfish(real_coords=coords, rand_coords=rand_coords, alt_coords=alt_coords)

            self.output_data = DataObj(real_df1, real_df2, rand_df1, rand_df2)
            # self.progress.emit(self.)
            self.finished.emit(self.output_data)
        except Exception as e:
            self.dlg = Logger()
            self.dlg.show()
            print(traceback.format_exc())
            logging.error(traceback.format_exc())
            self.finished.emit({})


class WorkflowPage(QWidget):
    """
    WORKFLOW PAGE
    __________________
    @coords: list containing csv coordinate data of gold particles scaled via scalar to proper unit
    @alt_coords: list containing csv coordinate data of gold particles as lighthouse population
    @wf: selected workflow, JSON object containing the following data:
        @type: ENUM type of Workflow
        @header: string displayed as "header"
        @desc: string displayed as "description" below header
        @graph: graph metadata:
            @title: title of graph
            @x_label: x_label of graph
            @y_label: y_label of graph
    @img: array of selected image paths
    @mask: array of selected mask paths
    @csv: array of selected csv paths
    @csv2: array of selected csv2 paths
    @output_ops.output_unit: metric output unit
    @output_ops.output_scalar: multiplier ratio between pixels and desired output metric unit
    @output_ops.output_dir: the directory to create output data in
    @output_ops.delete_old: delete output data older than 5 runs
    @pg: primary loading/progress bar ref
    """

    def __init__(self, wf: WorkflowObj, coords: List[Tuple[float, float]], alt_coords: List[Tuple[float, float]] = None, output_ops: OutputOptions = None, img: str = "", mask: str = "", csv: str = "", csv2: str = "", pg: Progress = None, log: Logger = None):
        super().__init__()
        # init class vars: allow referencing within functions without passing explicitly
        self.is_init = False
        self.data: DataObj
        self.wf = wf
        self.pg = pg
        # self.coords = coords
        # self.alt_coords = alt_coords
        self.output_ops = output_ops
        # create popup error logger
        self.dlg = log
        # init layout
        layout = QFormLayout()
        # header
        header = QLabel(wf['header'])
        header.setStyleSheet("font-size: 24px; font-weight: bold; padding-top: 8px; ")
        layout.addRow(header)
        desc = QLabel(wf['desc'])
        desc.setStyleSheet("font-size: 17px; font-weight: 400; padding-top: 3px; padding-bottom: 20px;")
        desc.setWordWrap(True)
        layout.addRow(desc)
        # REUSABLE PARAMETERS
        self.workflows_header = QLabel("Parameters")
        layout.addRow(self.workflows_header)
        # custom props
        self.cstm_props = []
        for i in range(len(wf['props'])):
            prop_l = QLabel(wf['props'][i]['title'])
            prop_l.setStyleSheet("font-size: 17px; font-weight: 400;")
            prop_le = QLineEdit()
            prop_le.setPlaceholderText(wf['props'][i]['placeholder'])
            layout.addRow(prop_l, prop_le)
            self.cstm_props.append(prop_le)
        # REAL COORDS SECTION
        file_head = QLabel("Selected Files")
        file_head.setStyleSheet(
            "font-size: 17px; font-weight: 500; padding-top: 0px; padding-bottom: 0px; margin-top: 0px; margin-bottom: 0px;")
        self.file_head_cb = QToolButton()
        self.file_head_cb.setArrowType(Qt.DownArrow)
        self.file_head_cb.setCursor(QCursor(Qt.PointingHandCursor))
        self.file_head_cb.clicked.connect(self.toggle_file_adv)
        layout.addRow(file_head, self.file_head_cb)
        # image path
        img_lb = QLabel("image")
        img_lb.setStyleSheet("font-size: 17px; font-weight: 400;")
        self.img_drop = QComboBox()
        self.img_drop.addItems([img])
        layout.addRow(img_lb, self.img_drop)  # csv
        # mask path
        mask_lb = QLabel("mask")
        mask_lb.setStyleSheet("font-size: 17px; font-weight: 400;")
        self.mask_drop = QComboBox()
        self.mask_drop.addItems([mask])
        layout.addRow(mask_lb, self.mask_drop)
        # csv
        csv_lb = QLabel("csv")
        csv_lb.setStyleSheet("font-size: 17px; font-weight: 400;")
        self.csv_drop = QComboBox()
        self.csv_drop.addItems([csv])
        layout.addRow(csv_lb, self.csv_drop)

        # hide hidden props by default
        self.real_props = [img_lb, self.img_drop, mask_lb, self.mask_drop, csv_lb, self.csv_drop]

        if len(csv2) > 0:
            csv2_lb = QLabel("csv2 (lighthouse pop)")
            csv2_lb.setStyleSheet("font-size: 17px; font-weight: 400;")
            self.csv2_drop = QComboBox()
            self.csv2_drop.addItems([csv])
            layout.addRow(csv2_lb, self.csv2_drop)
            self.real_props.append(csv2_lb)
            self.real_props.append(self.csv2_drop)

        for prop in self.real_props:
            prop.setHidden(True)
        # RANDOM COORDS SECTION
        theme_head = QLabel("Theme & Coords")
        theme_head.setStyleSheet(
            "font-size: 17px; font-weight: 500; padding-top: 0px; padding-bottom: 0px; margin-top: 0px; margin-bottom: 0px;")
        self.theme_cb = QToolButton()
        self.theme_cb.setArrowType(Qt.DownArrow)
        self.theme_cb.setCursor(QCursor(Qt.PointingHandCursor))
        self.theme_cb.clicked.connect(self.toggle_theme_adv)
        layout.addRow(theme_head, self.theme_cb)
        # color palette
        pal_lb = QLabel('<a href="https://seaborn.pydata.org/tutorial/color_palettes.html">color palette</a>')
        pal_lb.setOpenExternalLinks(True)
        pal_lb.setStyleSheet("font-size: 17px; font-weight: 400;")
        self.pal_type = QComboBox()
        self.pal_type.addItems(PALETTE_OPS)
        layout.addRow(pal_lb, self.pal_type)
        # palette random
        r_pal_lb = QLabel(
            '<a href="https://seaborn.pydata.org/tutorial/color_palettes.html">rand color palette</a>')
        r_pal_lb.setStyleSheet("font-size: 17px; font-weight: 400;")
        r_pal_lb.setOpenExternalLinks(True)
        self.r_pal_type = QComboBox()
        self.r_pal_type.addItems(PALETTE_OPS)
        self.r_pal_type.setCurrentText('crest')
        layout.addRow(r_pal_lb, self.r_pal_type)
        # num bins
        bars_lb = QLabel(
            '<a href="https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.hist.html"># hist bins</a>')
        bars_lb.setOpenExternalLinks(True)
        bars_lb.setStyleSheet("font-size: 17px; font-weight: 400;")
        self.bars_ip = QLineEdit()
        self.bars_ip.setPlaceholderText("10 OR [1, 2, 3, 4] OR 'fd'")
        layout.addRow(bars_lb, self.bars_ip)
        # num coords to gen
        n_coord_lb = QLabel("# of coords")
        n_coord_lb.setStyleSheet("font-size: 17px; font-weight: 400;")
        self.n_coord_ip = QLineEdit()
        self.n_coord_ip.setStyleSheet(
            "font-size: 16px; padding: 8px;  font-weight: 400; background: #ddd; border-radius: 7px;  margin-bottom: 5px; ")  # max-width: 200px;
        self.n_coord_ip.setPlaceholderText("default is # in real csv")
        layout.addRow(n_coord_lb, self.n_coord_ip)
        # set adv hidden by default
        self.theme_props = [pal_lb, self.pal_type, bars_lb, self.bars_ip, self.r_pal_type, r_pal_lb, n_coord_lb, self.n_coord_ip]
        for prop in self.theme_props:
            prop.setHidden(True)
        # output header
        self.out_header = QLabel("Output")
        layout.addRow(self.out_header)
        # toggleable output
        self.out_desc = QLabel("Check boxes to toggle output visualizations. Double-click on an image to open it.")
        self.out_desc.setStyleSheet("font-size: 17px; font-weight: 400; padding-top: 3px; padding-bottom: 20px;")
        self.out_desc.setWordWrap(True)
        layout.addRow(self.out_desc)
        # real
        self.gen_real_lb = QLabel("display real coords")
        self.gen_real_lb.setStyleSheet("margin-left: 50px; font-size: 17px; font-weight: 400;")
        self.gen_real_cb = QCheckBox()
        self.gen_real_cb.clicked.connect(partial(self.create_visuals, self.wf, (self.bars_ip.text() if self.bars_ip.text() else 'fd'), self.output_ops.output_unit, self.output_ops.output_scalar))
        self.gen_real_cb.setChecked(True)
        # rand
        self.gen_rand_lb = QLabel("display random coords")
        self.gen_rand_lb.setStyleSheet("margin-left: 50px; font-size: 17px; font-weight: 400;")
        self.gen_rand_cb = QCheckBox()
        self.gen_rand_cb.clicked.connect(partial(self.create_visuals, self.wf, (self.bars_ip.text() if self.bars_ip.text() else 'fd'), self.output_ops.output_unit, self.output_ops.output_scalar))
        # cb row
        cb_row = QHBoxLayout()
        cb_row.addWidget(self.gen_real_lb)
        cb_row.addWidget(self.gen_real_cb)
        cb_row.addWidget(self.gen_rand_lb)
        cb_row.addWidget(self.gen_rand_cb)
        layout.addRow(cb_row)
        # annotated image
        self.image_frame = QLabel()
        self.image_frame.setStyleSheet("padding-top: 3px; background: white;")
        self.image_frame.setMaximumSize(400, 250)
        self.image_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_frame.setCursor(QCursor(Qt.PointingHandCursor))
        self.image_frame.mouseDoubleClickEvent = lambda event: self.open_large(event, self.display_img)
        # graph
        self.graph_frame = QLabel()
        self.graph_frame.setStyleSheet("padding-top: 3px; background: white;")
        self.graph_frame.setMaximumSize(400, 250)
        self.graph_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.graph_frame.mouseDoubleClickEvent = lambda event: self.open_large(event, self.graph)
        self.graph_frame.setCursor(QCursor(Qt.PointingHandCursor))
        # container for visualizers
        self.img_cont = QHBoxLayout()
        self.img_cont.addWidget(self.image_frame)
        self.img_cont.addWidget(self.graph_frame)
        layout.addRow(self.img_cont)
        # loading bar
        self.progress = QProgressBar(self)
        self.progress.setGeometry(0, 0, 300, 25)
        self.progress.setMaximum(100)
        layout.addRow(self.progress)
        # run & download btns
        self.run_btn = QPushButton('Run Again', self)
        self.run_btn.setStyleSheet(
            "font-size: 16px; font-weight: 600; padding: 8px; margin-top: 3px; background: #E89C12; color: white; border-radius: 7px; ")
        self.run_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.run_btn.clicked.connect(partial(self.run, wf, coords))
        self.download_btn = QPushButton('Download Again', self)
        self.download_btn.setStyleSheet(
            "font-size: 16px; font-weight: 600; padding: 8px; margin-top: 3px; background: #ccc; color: white; border-radius: 7px; ")
        self.download_btn.clicked.connect(partial(self.download, output_ops, wf))
        self.download_btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn_r = QHBoxLayout()
        btn_r.addWidget(self.run_btn)
        btn_r.addWidget(self.download_btn)
        layout.addRow(btn_r)
        # assign layout
        self.setLayout(layout)
        # run on init
        self.run(wf, coords, alt_coords)

    def update_progress(self, value: int):
        """ UPDATE PROGRESS BAR """
        self.progress.setValue(value)

    def toggle_file_adv(self):
        """ TOGGLE GENERAL ADV OPTIONS """
        self.file_head_cb.setArrowType(Qt.UpArrow if self.file_head_cb.arrowType() == Qt.DownArrow else Qt.DownArrow)
        for prop in self.real_props:
            prop.setVisible(not prop.isVisible())

    def toggle_theme_adv(self):
        """ TOGGLE RAND ADV OPTIONS """
        self.theme_cb.setArrowType(
            Qt.UpArrow if self.theme_cb.arrowType() == Qt.DownArrow else Qt.DownArrow)
        for prop in self.theme_props:
            prop.setVisible(not prop.isVisible())

    def get_custom_values(self):
        return [self.cstm_props[i].text() if self.cstm_props[i].text() else self.wf['props'][i]['placeholder'] for i in range(len(self.cstm_props))]

    def download(self, output_ops: OutputOptions, wf: WorkflowObj):
        print('download')
        self.dl_thread = QThread()
        self.dl_worker = DownloadWorker()
        self.dl_worker.moveToThread(self.dl_thread)
        self.dl_thread.started.connect(partial(self.dl_worker.run, wf, self.data, output_ops, self.img_drop.currentText(), self.display_img, self.graph))
        self.dl_worker.finished.connect(self.dl_thread.quit)
        self.dl_worker.finished.connect(self.dl_worker.deleteLater)
        self.dl_thread.finished.connect(self.dl_thread.deleteLater)
        # self.dl_worker.progress.connect(self.on_receive_data)
        self.dl_thread.start()

    def run(self, wf: WorkflowObj, coords: List[Tuple[float, float]], alt_coords: List[Tuple[float, float]]):
        """ RUN WORKFLOW """
        try:
            prog_wrapper = Progress()
            prog_wrapper.prog.connect(self.update_progress)

            self.rand_coords = gen_random_coordinates(img_path=self.img_drop.currentText(), mask_path=self.mask_drop.currentText(), count=int(self.n_coord_ip.text()) if self.n_coord_ip.text() else len(coords))

            vals = self.get_custom_values()

            self.thread = QThread()
            self.worker = AnalysisWorker()
            self.worker.moveToThread(self.thread)
            # self.thread.started.connect(partial(self.worker.run, wf, vals, prog_wrapper, coords, self.rand_coords, self.img_drop.currentText(), self.mask_drop.currentText(), alt_coords))
            self.thread.started.connect(partial(self.worker.run, wf, vals, coords, self.rand_coords, alt_coords, self.img_drop.currentText(), self.mask_drop.currentText(), ))
            self.worker.progress.connect(self.update_progress)
            self.worker.finished.connect(self.on_receive_data)
            self.worker.finished.connect(self.thread.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.thread.finished.connect(self.thread.deleteLater)
            self.thread.start()
        except Exception as e:
            self.handle_except(traceback.format_exc())

    def on_receive_data(self, output_data: DataObj):
        try:
            self.data = output_data
            # TODO: handle this better 
            # create ui scheme
            self.create_visuals(wf=self.wf, n_bins=(self.bars_ip.text() if self.bars_ip.text() else 'fd'), output_ops=self.output_ops)
            # # download files automatically
            self.download(output_ops=self.output_ops, wf=self.wf)
            self.download_btn.setStyleSheet(
                "font-size: 16px; font-weight: 600; padding: 8px; margin-top: 3px; background: #007267; color: white; border-radius: 7px; ")
            self.progress.setValue(100)

            if self.is_init is False:
                self.pg()
                self.is_init = True
        except Exception as e:
            self.handle_except(traceback.format_exc())


    def create_visuals(self, wf: WorkflowObj, n_bins, output_ops: OutputOptions, n: List[int] = np.zeros(11)):
        """ CREATE DATA VISUALIZATIONS """
        try:
            if self.gen_real_cb.isChecked() or self.gen_rand_cb.isChecked() and len(self.real_coords) > 0:
                print("generating visualizations")
                plt.close('all')
                graph_df = pd.DataFrame([])
                cm = plt.cm.get_cmap('crest')
                fig = plt.figure()
                canvas = FigureCanvas(fig)
                ax = fig.add_subplot(111)

                # fix csv index not matching id
                self.data.real_df1.sort_values(wf["graph"]["x_type"], inplace=True)
                self.data.real_df1 = self.data.real_df1.reset_index(drop=True)
                self.data.final_real = pixels_conversion(data=self.data.real_df1, unit=output_ops.output_unit, scalar=output_ops.output_scalar)
                if wf["graph"]["x_type"] in self.data.rand_df1.columns and len(self.data.rand_df1[wf["graph"]["x_type"]]) > 0:
                    self.data.rand_df1.sort_values(wf["graph"]["x_type"], inplace=True)
                    self.data.rand_df1 = self.data.rand_df1.reset_index(drop=True)
                if not self.data.rand_df1.empty:
                    self.data.final_rand = pixels_conversion(data=self.data.rand_df1, unit=output_ops.output_unit, scalar=output_ops.output_scalar)

                # convert back to proper size
                if wf["graph"]["type"] == "hist":
                    # create histogram
                    if self.gen_real_cb.isChecked() and not self.gen_rand_cb.isChecked():
                        graph_df = self.data.final_real[wf["graph"]["x_type"]]
                        cm = sns.color_palette(self.pal_type.currentText(), as_cmap=True)
                        ax.set_title(f'{wf["graph"]["title"]} (Real)')
                    elif self.gen_rand_cb.isChecked() and not self.gen_real_cb.isChecked():
                        ax.set_title(f'{wf["graph"]["title"]} (Rand)')
                        cm = sns.color_palette(self.r_pal_type.currentText(), as_cmap=True)
                        graph_df = self.data.final_rand[wf["graph"]["x_type"]]
                    if self.gen_real_cb.isChecked() and not self.gen_rand_cb.isChecked() or self.gen_rand_cb.isChecked() and not self.gen_real_cb.isChecked():
                        # draw graph
                        n, bins, patches = ax.hist(graph_df, bins=(int(n_bins) if n_bins.isdecimal() else n_bins), color='green')
                        # normalize values
                        col = (n - n.min()) / (n.max() - n.min())
                        for c, p in zip(col, patches):
                            p.set_facecolor(cm(c))
                    elif self.gen_real_cb.isChecked() and self.gen_rand_cb.isChecked():
                        rand_graph = self.data.final_rand[wf["graph"]["x_type"]]
                        real_graph = self.data.final_real[wf["graph"]["x_type"]]
                        ax.hist(rand_graph, bins=(int(n_bins) if n_bins.isdecimal() else n_bins), alpha=0.75, color=create_color_pal(n_bins=1, palette_type=self.r_pal_type.currentText()), label='Rand')
                        n, bins, patches = ax.hist(real_graph, bins=(int(n_bins) if n_bins.isdecimal() else n_bins), alpha=0.75, color=create_color_pal(n_bins=1, palette_type=self.pal_type.currentText()), label='Real')
                        ax.set_title(f'{wf["graph"]["title"]} (Real & Rand)')
                        ax.legend(loc='upper right')
                elif wf["graph"]["type"] == "line":
                    # create line graph
                    if self.gen_real_cb.isChecked():
                        cm = sns.color_palette(self.pal_type.currentText(), as_cmap=True)
                        ax.set_title(f'{wf["graph"]["title"]} (Real)')
                        graph_df = self.data.final_real
                    elif self.gen_rand_cb.isChecked():
                        ax.set_title(f'{wf["graph"]["title"]} (Rand)')
                        cm = sns.color_palette(self.r_pal_type.currentText(), as_cmap=True)
                        graph_df = self.data.final_rand
                    ax.plot(graph_df[wf["graph"]["x_type"]], graph_df[wf["graph"]["y_type"]], color='blue')
                elif wf["graph"]["type"] == "bar":
                    # create bar graph
                    if self.gen_real_cb.isChecked():
                        c = 1
                        ax.set_title(f'{wf["graph"]["title"]} (Real)')
                        graph_y = self.data.final_rand[wf["graph"]["y_type"]],
                        graph_x = np.array(self.data.final_real[wf["graph"]["x_type"]])
                        # print(self.real_df[wf["graph"]["y_type"]], np.array(self.real_df[wf["graph"]["y_type"]]))
                        if wf['type'] == Workflow.CLUST:
                            graph_y = np.bincount(np.bincount(self.data.final_real[wf["graph"]["x_type"]]))[1:]
                            graph_x = list(range(1, (len(graph_y) + 1)))
                            c = len(graph_x)
                        c = create_color_pal(n_bins=c, palette_type=self.pal_type.currentText())
                        n = graph_x
                    elif self.gen_rand_cb.isChecked():
                        ax.set_title(f'{wf["graph"]["title"]} (Rand)')
                        c = 1
                        graph_y = self.data.final_rand[wf["graph"]["y_type"]],
                        graph_x = np.array(self.data.final_real[wf["graph"]["x_type"]])
                        if wf['type'] == Workflow.CLUST:
                            graph_y = np.bincount(np.bincount(self.data.final_rand[wf["graph"]["x_type"]]))[1:]
                            graph_x = list(range(1, (len(graph_y)+1)))
                            c = len(graph_x)
                        c = create_color_pal(n_bins=c, palette_type=self.r_pal_type.currentText())
                        n = graph_x
                    if self.gen_real_cb.isChecked() and not self.gen_rand_cb.isChecked() or self.gen_rand_cb.isChecked() and not self.gen_real_cb.isChecked():
                        if wf['type'] == Workflow.RIPPLER:
                            # print(graph_y[0].values)
                            ax.bar(graph_x, graph_y[0].values, width=20, color=c)
                        else:
                            # print('bar', graph_x, graph_y)
                            bar_plot = ax.bar(graph_x, graph_y, color=c)
                            for idx, rect in enumerate(bar_plot):
                                height = rect.get_height()
                                ax.text(rect.get_x() + rect.get_width() / 2., 1.05 * height,
                                        graph_y[idx],
                                        ha='center', va='bottom', rotation=0)

                    elif self.gen_real_cb.isChecked() and self.gen_rand_cb.isChecked():
                        real_graph_y = np.bincount(np.bincount(self.data.final_real[wf["graph"]["x_type"]]))[1:]
                        real_graph_x = list(range(1, (len(set(real_graph_y)))+1))
                        rand_graph_y = np.bincount(np.bincount(self.data.final_rand[wf["graph"]["x_type"]]))[1:]
                        rand_graph_x = list(range(1, (len(set(rand_graph_y)))+1))
                        if wf['type'] == Workflow.RIPPLER:
                            ax.bar([el - 5 for el in np.array(self.data.final_rand[wf["graph"]["x_type"]])], np.array(self.data.final_rand[wf["graph"]["y_type"]]), width=20, alpha=0.7, color=create_color_pal(n_bins=1, palette_type=self.r_pal_type.currentText()), label='Rand')
                            ax.bar([el + 5 for el in np.array(self.data.final_real[wf["graph"]["x_type"]])], np.array(self.data.final_real[wf["graph"]["y_type"]]), width=20, alpha=0.7, color=create_color_pal(n_bins=1, palette_type=self.pal_type.currentText()), label='Real')
                        else:
                            ax.bar(rand_graph_x, rand_graph_y, color=create_color_pal(n_bins=len(rand_graph_x), palette_type=self.r_pal_type.currentText()), alpha=0.7,  label='Rand')
                            ax.bar(real_graph_x, real_graph_y, color=create_color_pal(n_bins=len(real_graph_x), palette_type=self.pal_type.currentText()),  alpha=0.7, label='Real')
                        ax.set_title(f'{wf["graph"]["title"]} (Real & Rand)')
                        ax.legend(loc='upper right')
                        n = rand_graph_x

                        # label graph
                ax.set_xlabel(f'{wf["graph"]["x_label"]} ({enum_to_unit(output_ops.output_unit)})')
                ax.set_ylabel(wf["graph"]["y_label"])
                ax.set_ylim(ymin=0)
                print("generated graphs")
                # generate palette
                palette = create_color_pal(n_bins=int(len(n)), palette_type=self.pal_type.currentText())
                r_palette = create_color_pal(n_bins=int(len(n)), palette_type=self.r_pal_type.currentText())
                # draw on canvas
                canvas.draw()
                # determine shape of canvas
                size = canvas.size()
                width, height = size.width(), size.height()
                # set graph to image of plotted hist
                self.graph = QImage(canvas.buffer_rgba(), width, height, QImage.Format_ARGB32)
                # load in image
                drawn_img = cv2.imread(self.img_drop.currentText())
                print("loaded img")
                # display img
                pixmap = QPixmap.fromImage(self.graph)
                smaller_pixmap = pixmap.scaled(300, 250, Qt.KeepAspectRatio, Qt.FastTransformation)
                self.graph_frame.setPixmap(smaller_pixmap)
                # TODO: ADD NEW GRAPHS HERE
                if wf["type"] == Workflow.NND:
                    # if real coords selected, annotate them on img with lines indicating length
                    if self.gen_real_cb.isChecked():
                        drawn_img = draw_length(nnd_df=self.data.real_df1, bin_counts=n, img=drawn_img, palette=palette, circle_c=(103, 114, 0))
                    # if rand coords selected, annotate them on img with lines indicating length
                    if self.gen_rand_cb.isChecked():
                        drawn_img = draw_length(nnd_df=self.data.rand_df1, bin_counts=n, img=drawn_img, palette=r_palette, circle_c=(18, 156, 232))
                elif wf["type"] == Workflow.CLUST:
                    vals = self.get_custom_values()
                    if self.gen_real_cb.isChecked():
                        drawn_img = draw_clust(clust_df=self.data.real_df1, img=drawn_img, palette=palette, distance_threshold=vals[0], draw_clust_area=vals[2])
                    if self.gen_rand_cb.isChecked():
                        drawn_img = draw_clust(clust_df=self.data.rand_df1, img=drawn_img, palette=r_palette, distance_threshold=vals[0], draw_clust_area=vals[2])
                elif wf["type"] == Workflow.NND_CLUST:
                    if self.gen_real_cb.isChecked():
                        drawn_img = draw_nnd_clust(nnd_df=self.data.real_df1, clust_df=self.data.real_df2, img=drawn_img,
                                                   palette=palette, bin_counts=n, circle_c=(103, 114, 0), )
                    if self.gen_rand_cb.isChecked():
                        drawn_img = draw_nnd_clust(nnd_df=self.data.rand_df1, clust_df=self.data.rand_df2, img=drawn_img,
                                                   palette=r_palette, bin_counts=n, circle_c=(18, 156, 232), )
                elif wf["type"] == Workflow.RIPPLER:
                    vals = [self.cstm_props[i].text() if self.cstm_props[i].text() else wf['props'][i]['placeholder'] for i in range(len(self.cstm_props))]
                    if self.gen_real_cb.isChecked():
                        drawn_img = draw_rippler(coords=self.real_coords, alt_coords=self.alt_coords, mask_path=self.mask_drop.currentText(), img=drawn_img, palette=palette, circle_c=(18, 156, 232), max_steps=vals[0], step_size=vals[1])
                    if self.gen_rand_cb.isChecked():
                        drawn_img = draw_rippler(coords=self.rand_coords, alt_coords=self.alt_coords, mask_path=self.mask_drop.currentText(), img=drawn_img, palette=r_palette, circle_c=(103, 114, 0), max_steps=vals[0], step_size=vals[1])
                elif wf["type"] == Workflow.STARFISH:
                    # if real coords selected, annotate them on img with lines indicating length
                    if self.gen_real_cb.isChecked():
                        drawn_img = draw_starfish(nnd_df=self.data.real_df1, bin_counts=n, img=drawn_img, palette=palette, circle_c=(103, 114, 0))
                    # if rand coords selected, annotate them on img with lines indicating length
                    if self.gen_rand_cb.isChecked():
                        drawn_img = draw_starfish(nnd_df=self.data.rand_df1, bin_counts=n, img=drawn_img, palette=r_palette, circle_c=(18, 156, 232))
                # end graph display, set display img to annotated image
                # https://stackoverflow.com/questions/33741920/convert-opencv-3-iplimage-to-pyqt5-qimage-qpixmap-in-python
                height, width, bytesPerComponent = drawn_img.shape
                bytesPerLine = 3 * width
                cv2.cvtColor(drawn_img, cv2.COLOR_BGR2RGB, drawn_img)
                self.display_img = QImage(drawn_img.data, width, height, bytesPerLine, QImage.Format_RGB888)
                print("drew display imgs")
                # resize to fit on gui
                pixmap = QPixmap.fromImage(self.display_img)
                print("drew pixmap")
                smaller_pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.FastTransformation)
                print("scale pixmap")
                self.image_frame.setPixmap(smaller_pixmap)
                print("finished generating visuals")

        except Exception as e:
            self.error_gif = QMovie("./images/caterror.gif")
            self.image_frame.setMovie(self.error_gif)
            self.error_gif.start()
            self.handle_except(traceback.format_exc())

    def open_large(self, event, img: QImage):
        """ OPEN IMAGE IN VIEWER """
        try:
            self.image_viewer = QImageViewer(img)
            self.image_viewer.show()
        except Exception as e:
            self.handle_except(traceback.format_exc())

    def handle_except(self, trace="An error occurred"):
        if not self.dlg.isVisible():
            self.dlg.show()
        print(trace)
        logging.error(trace)


class DownloadWorker(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(object)
    # TODO: actually use otuput dir

    def run(self, wf: WorkflowObj, data: DataObj, output_ops: OutputOptions, img: str, display_img: QImage, graph: QImage):
        """ DOWNLOAD FILES """
        try:
            out_start = output_ops.output_dir if output_ops.output_dir is not None else './output'
            # delete old files to make space if applicable
            o_dir = f'{out_start}/{wf["name"].lower()}'
            if output_ops.delete_old:
                while len(os.listdir(o_dir)) >= MAX_DIRS_PRUNE:
                    oldest_dir = \
                        sorted([os.path.abspath(
                            f'{o_dir}/{f}') for f in os.listdir(o_dir)], key=os.path.getctime)[0]
                    print("pruning ", oldest_dir)
                    shutil.rmtree(oldest_dir)
                print("pruned old output")
        except Exception as e:
            self.dlg = Logger()
            self.dlg.show()
            logging.error(traceback.format_exc())
            self.finished.emit()
          
        # download files
        try:
            print("prepare to download output")
            img_name = os.path.splitext(
                os.path.basename(img))[0]
            out_dir = f'{out_start}/{wf["name"].lower()}/{img_name}-{datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}'
            os.makedirs(out_dir, exist_ok=True)
            data.final_real.to_csv(f'{out_dir}/real_{wf["name"].lower()}_output_{enum_to_unit(output_ops.output_unit)}.csv',
                                   index=False, header=True)
            data.final_rand.to_csv(f'{out_dir}/rand_{wf["name"].lower()}_output_{enum_to_unit(output_ops.output_unit)}.csv',
                                   index=False, header=True)
            if display_img:
                display_img.save(
                    f'{out_dir}/drawn_{wf["name"].lower()}_img.tif')
            else:
                print(
                    'no display image generated. An error likely occurred running workflow.')
            graph.save(f'{out_dir}/{wf["name"].lower()}_graph.jpg')
            # if workflow fills full dfs, output those two
            if not data.real_df2.empty and not data.rand_df2.empty:
                data.real_df2 = pixels_conversion(
                    data=data.real_df2, unit=output_ops.output_unit, scalar=output_ops.output_scalar)
                data.rand_df2 = pixels_conversion(
                    data=data.rand_df2, unit=output_ops.output_unit, scalar=output_ops.output_scalar)
                data.real_df2.to_csv(
                    f'{out_dir}/detailed_real_{wf["name"].lower()}_output_{enum_to_unit(output_ops.output_unit)}.csv', index=False,
                    header=True)
                data.rand_df2.to_csv(
                    f'{out_dir}/detailed_rand_{wf["name"].lower()}_output_{enum_to_unit(output_ops.output_unit)}.csv', index=False,
                    header=True)
            print("downloaded output")
        except Exception as e:
            self.dlg = Logger()
            self.dlg.show()
            logging.error(traceback.format_exc())
            self.finished.emit()
          
