# views
from time import sleep

from globals import WORKFLOWS, NAV_ICON
from views.home import HomePage
from typings import Unit
from utils import pixels_conversion, unit_to_enum
from views.logger import Logger
from views.workflow import WorkflowPage
# stylesheet
from styles.stylesheet import styles
# pyQT5
from PyQt5.QtCore import Qt, QSize, QObject, pyqtSignal, QThread
from PyQt5.QtGui import QIcon, QCursor
from PyQt5.QtWidgets import (QWidget, QListWidget, QStackedWidget, QHBoxLayout, QListWidgetItem, QApplication)
# general
import sys
from functools import partial

class AnalysisWorker(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(int)

    def run(self, img_drop, mask_drop, csv_drop, s, ou, dod, update_main_progress, workflow_cbs, page_stack, nav_list, scaled_df):
        # add page tabs
        for i in range(len(WORKFLOWS)):
            update_main_progress(i * 20)
            if workflow_cbs[i].isChecked():
                item = QListWidgetItem(
                    NAV_ICON, str(WORKFLOWS[i]['name']), nav_list)
                item.setSizeHint(QSize(60, 60))
                item.setTextAlignment(Qt.AlignCenter)
                # generate workflow page
                print(WORKFLOWS[i])
                page_stack.addWidget(
                    WorkflowPage(df=scaled_df,
                                 wf=WORKFLOWS[i],
                                 img=img_drop,
                                 mask=mask_drop,
                                 csv=csv_drop,
                                 scalar=s,
                                 input_unit=Unit.PIXEL,
                                 output_unit=ou,
                                 delete_old=dod
                                 )
                )
        # for i in range(5):
        #     sleep(1)
            self.progress.emit((i / len(WORKFLOWS)) * 100)
        self.finished.emit()


class GoldInAndOut(QWidget):
    """ PARENT WINDOW INITIALIZATION """
    def __init__(self):
        super().__init__()
        self.setWindowTitle('GoldInAndOut')
        self.setWindowIcon(QIcon('./assets/logo.png'))
        self.setMinimumSize(QSize(900, 950))
        self.setMaximumSize(QSize(900, 950))
        # layout with list on left and stacked widget on right
        layout = QHBoxLayout(self, spacing=0)
        layout.setContentsMargins(0, 0, 0, 0)
        self.nav_list = QListWidget(self)
        layout.addWidget(self.nav_list)
        self.page_stack = QStackedWidget(self)
        layout.addWidget(self.page_stack)
        # add main page
        self.home_page = HomePage(start=self.init_workflows)
        # init ui
        self.init_ui()

    def init_ui(self):
        """ INITIALIZE MAIN CHILD WINDOW """
        self.nav_list.currentRowChanged.connect(self.page_stack.setCurrentIndex)
        self.nav_list.setFrameShape(QListWidget.NoFrame)
        self.nav_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav_list.setCursor(QCursor(Qt.PointingHandCursor))
        # add main page to nav
        item = QListWidgetItem(
            NAV_ICON, str("Main"), self.nav_list)
        item.setSizeHint(QSize(60, 60))
        item.setTextAlignment(Qt.AlignCenter)
        # add each page to parent window stack
        self.page_stack.addWidget(self.home_page)
        # select first page by default
        self.nav_list.item(0).setSelected(True)

    def on_run_complete(self):
        self.home_page.start_btn.setEnabled(True)
        self.home_page.start_btn.setText("Run Again")
        self.home_page.start_btn.setStyleSheet("font-size: 16px; font-weight: 600; padding: 8px; margin-top: 10px; margin-right: 450px; color: white; border-radius: 7px; background: #E89C12")
        self.update_main_progress(100)

    def init_workflows(self):
        """ INITIALIZE CHILD WORKFLOW WINDOWS """
        # open logger if applicable
        if self.home_page.show_logs.isChecked():
            self.dlg = Logger()
            self.dlg.show()

        self.empty_stack()
        self.load_data()

        # TODO: remove when no longer using for testing
        img_drop = [self.home_page.img_le.text()] if len(self.home_page.img_le.text()) > 0 else ["./input/example_image.tif"]
        mask_drop = [self.home_page.mask_le.text()] if len(self.home_page.mask_le.text()) > 0 else ["./input/example_mask.tif"]
        csv_drop = [self.home_page.csv_le.text()] if len(self.home_page.csv_le.text()) > 0 else ["./input/example_csv.csv"]
        # input/output units
        # TODO: iu = unit_to_enum(self.home_page.ip_scalar_type.currentText() if self.home_page.ip_scalar_type.currentText() is not None else 'px')
        ou = unit_to_enum(self.home_page.op_scalar_type.currentText() if self.home_page.op_scalar_type.currentText() is not None else 'px')
        # scalar
        s = float(self.home_page.csvs_ip.text() if len(self.home_page.csvs_ip.text()) > 0 else 1)
        dod = self.home_page.dod_cb.isChecked()

        self.thread = QThread()
        self.worker = AnalysisWorker()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(partial(self.worker.run, img_drop, mask_drop, csv_drop, s, ou, dod, self.update_main_progress, self.home_page.workflow_cbs, self.page_stack, self.nav_list, self.SCALED_DF))
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.progress.connect(self.update_main_progress)
        self.thread.start()
        # disable start button while performing analysis
        self.home_page.start_btn.setEnabled(False)
        self.home_page.start_btn.setStyleSheet("font-size: 16px; font-weight: 600; padding: 8px; margin-top: 10px; margin-right: 450px; background: #ddd; color: white; border-radius: 7px; ")
        self.thread.finished.connect(self.on_run_complete)


    def load_data(self):
        """ LOAD AND SCALE DATA """
        path = self.home_page.csv_le.text() if len(self.home_page.csv_le.text()) > 0 else "./input/example_csv.csv"
        # TODO: unit = unit_to_enum(self.home_page.ip_scalar_type.currentText()) if self.home_page.ip_scalar_type.currentText() else Unit.PIXEL
        scalar = float(self.home_page.csvs_ip.text() if len(self.home_page.csvs_ip.text()) > 0 else 1)
        self.SCALED_DF = pixels_conversion(csv_path=path, input_unit=Unit.PIXEL, csv_scalar=scalar)

    def update_main_progress(self, value):
        """ UPDATE PROGRESS BAR """
        self.home_page.progress.setValue(value)

    def empty_stack(self):
        """ CLEAR PAGE/NAV STACKS """
        for i in range(self.page_stack.count()-1, 0, -1):
            if i > 0:
                self.nav_list.takeItem(i)
                self.page_stack.removeWidget(self.page_stack.widget(i))


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet(styles)
    app.setStyle("fusion")
    gui = GoldInAndOut()
    gui.show()
    sys.exit(app.exec_())
