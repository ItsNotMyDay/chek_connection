import sys
import os
import json
import platform
import subprocess
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLineEdit, QScrollArea, QGraphicsDropShadowEffect, QLabel)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt, QPropertyAnimation, QEasingCurve, QPoint
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush

CONFIG_FILE = "config.json"
PING_INTERVAL_MS = 2000
TIMEOUT_MS = 1000
DELAY_YELLOW_MS = 80 # Снизили порог для более чуткой реакции на задержку

MODERN_STYLE = """
QWidget#MainWindow {
    background: qlineargradient(spread:pad, x1:0, y1:0, x2:0, y2:1, stop:0 #111219, stop:1 #0A0B10);
    font-family: 'Inter', 'Segoe UI', sans-serif;
}

QScrollArea {
    border: none;
    background: transparent;
}

QScrollArea > QWidget > QWidget {
    background: transparent;
}

QLineEdit {
    background-color: transparent;
    color: #FFFFFF;
    border: none;
    border-bottom: 2px solid #222533;
    padding: 6px 4px;
    font-size: 14px;
    font-weight: 500;
}

QLineEdit:focus {
    border-bottom: 2px solid #6366F1;
    color: #F8FAFC;
}

QLineEdit::placeholder {
    color: #475569;
}

QPushButton#btnDelete {
    background-color: #1E2030;
    color: #94A3B8;
    border: 1px solid #2D3149;
    border-radius: 8px;
    font-size: 14px;
    font-weight: bold;
}

QPushButton#btnDelete:hover {
    background-color: #7F1D1D;
    color: #FCA5A5;
    border: 1px solid #991B1B;
}

QScrollBar:vertical {
    border: none;
    background: transparent;
    width: 6px;
}

QScrollBar::handle:vertical {
    background: #334155;
    border-radius: 3px;
}

QScrollBar::handle:vertical:hover {
    background: #475569;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    border: none;
    background: none;
}
"""

class PingWorker(QThread):
    result_ready = pyqtSignal(str, str, float)

    def __init__(self, ip):
        super().__init__()
        self.ip = ip

    def run(self) -> None:
        ip = self.ip.strip()
        if not ip:
            self.result_ready.emit(self.ip, "red", 0.0)
            return

        current_os = platform.system().lower()
        if current_os == "windows":
            cmd = ["ping", "-n", "1", "-w", str(TIMEOUT_MS), ip]
        else:
            cmd = ["ping", "-c", "1", "-W", "1", ip]

        try:
            startupinfo = None
            if current_os == "windows":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            # Запускаем пинг БЕЗ text=True, чтобы самостоятельно декодировать байты
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                timeout=2.0, startupinfo=startupinfo
            )
            
            # Пробуем расшифровать вывод консоли Windows (cp866), если не вышло — берем utf-8
            try:
                output_text = result.stdout.decode('cp866')
            except Exception:
                output_text = result.stdout.decode('utf-8', errors='ignore')

            if result.returncode == 0:
                delay = self._parse_delay(output_text, current_os)
                status = "yellow" if delay > DELAY_YELLOW_MS else "green"
            else:
                status = "red"
                delay = 0.0
        except Exception as e:
            print(f"Критическая ошибка в потоке пинга: {e}")
            status = "red"
            delay = 0.0

        self.result_ready.emit(self.ip, status, delay)

    def _parse_delay(self, output: str, current_os: str) -> float:
        if current_os != "windows":
            return 0.0

        try:
            # Переводим всё в нижний регистр для надежности
            text = output.lower()
            
            # Способ 1: Ищем по строке статистики "среднее =" или "average ="
            for line in text.splitlines():
                if "среднее" in line or "average" in line:
                    # Разбиваем строку по знаку "=" и берем правую часть
                    parts = line.split("=")
                    if len(parts) > 1:
                        # Оставляем только цифры из правой части
                        digits = "".join([ch for ch in parts[-1] if ch.isdigit()])
                        if digits:
                            return float(digits)

            # Способ 2: Если не нашли статистику, ищем в строках ответов (время-346мс или время=346мс)
            for line in text.splitlines():
                if "время" in line or "time" in line:
                    # Заменяем дефисы на знаки равенства, чтобы проще делить
                    line_fixed = line.replace("-", "=").replace("<", "=")
                    parts = line_fixed.split("=")
                    if len(parts) > 1:
                        # Забираем первое слово после знака "=" (например, "346мс")
                        after_equal = parts[-1].strip().split()[0]
                        digits = "".join([ch for ch in after_equal if ch.isdigit()])
                        if digits:
                            return float(digits)
        except Exception as e:
            print(f"Ошибка ручного парсинга текста: {e}")
            
        return 0.0

class DynamicIndicator(QWidget):
    """Живой пульсирующий индикатор состояния сети."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(24, 24)
        self.base_color = QColor("#475569")
        self.glow_color = QColor("#475569")
        self.pulse_radius = 6.0
        self.growing = True

        # Внутренний таймер анимации пульсации
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate_pulse)
        self.timer.start(50)

    def set_status(self, status: str):
        if status == "green":
            self.base_color = QColor("#10B981")
            self.glow_color = QColor(16, 185, 129, 60)
        elif status == "yellow":
            self.base_color = QColor("#F59E0B")
            self.glow_color = QColor(245, 158, 11, 60)
        elif status == "red":
            self.base_color = QColor("#EF4444")
            self.glow_color = QColor(239, 68, 68, 60)
        else:
            self.base_color = QColor("#475569")
            self.glow_color = QColor(71, 85, 105, 60)
        self.update()

    def animate_pulse(self):
        if self.growing:
            self.pulse_radius += 0.3
            if self.pulse_radius >= 11.0:
                self.growing = False
        else:
            self.pulse_radius -= 0.3
            if self.pulse_radius <= 6.0:
                self.growing = True
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        center_x, center_y = self.width() / 2, self.height() / 2
        
        # Рисуем волну пульсации
        painter.setBrush(QBrush(self.glow_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPoint(int(center_x), int(center_y)), int(self.pulse_radius), int(self.pulse_radius))
        
        # Рисуем ядро
        painter.setBrush(QBrush(self.base_color))
        painter.drawEllipse(QPoint(int(center_x), int(center_y)), 5, 5)


class MiniHistogram(QWidget):
    """Мини-график задержки внутри карточки хоста."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(60, 20)
        self.delay = 0.0
        self.status = "red"

    def update_delay(self, delay: float, status: str):
        self.delay = delay
        self.status = status
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Фон подложки графика
        painter.setBrush(QColor("#1A1C28"))
        painter.setPen(QPen(QColor("#2D3149"), 1))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 4, 4)
        
        if self.status == "red" or self.delay <= 0:
            return

        # Рассчитываем ширину заполнения
        max_expected_delay = 200.0
        fill_ratio = min(self.delay / max_expected_delay, 1.0)
        fill_width = int((self.width() - 4) * fill_ratio)
        fill_width = max(fill_width, 4)

        if self.status == "green":
            color = QColor("#10B981")
        else:
            color = QColor("#F59E0B")

        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(2, 2, fill_width, self.height() - 4, 2, 2)


class HostCardWidget(QWidget):
    """Строка, стилизованная под неоновую интерактивную карточку хоста."""
    removed = pyqtSignal(QWidget)
    data_changed = pyqtSignal()

    def __init__(self, ip="", comment="", parent=None):
        super().__init__(parent)
        self.setObjectName("HostCard")
        
        self.setStyleSheet("""
            QWidget#HostCard {
                background-color: #161824;
                border: 1px solid #23263B;
                border-radius: 12px;
            }
            QWidget#HostCard:hover {
                border: 1px solid #4F46E5;
                background-color: #1A1C2C;
            }
        """)

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(12, 10, 12, 10)
        self.layout.setSpacing(12)

        # Динамический индикатор
        self.indicator = DynamicIndicator()
        self.layout.addWidget(self.indicator)

        # Инпуты
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Адрес хоста / IP")
        self.input_field.setMinimumWidth(130)
        self.input_field.setText(ip)
        self.layout.addWidget(self.input_field)

        self.comment_field = QLineEdit()
        self.comment_field.setPlaceholderText("Метка / Описание")
        self.comment_field.setMinimumWidth(200) # Увеличили ширину, так как место освободилось
        self.comment_field.setText(comment)
        self.comment_field.setStyleSheet("QLineEdit { color: #64748B; font-size: 12px; font-weight: normal; } QLineEdit:focus { color: #94A3B8; }")
        self.layout.addWidget(self.comment_field)

        # Лейбл задержки текстом
        self.lbl_delay = QLabel("-- мс")
        self.lbl_delay.setFixedSize(60, 20)
        self.lbl_delay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_delay.setStyleSheet("color: #475569; font-weight: bold; font-size: 12px;")
        self.layout.addWidget(self.lbl_delay)

        # Кнопка удаления
        self.btn_delete = QPushButton("×")
        self.btn_delete.setObjectName("btnDelete")
        self.btn_delete.setFixedSize(28, 28)
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        self.layout.addWidget(self.btn_delete)

        self.current_ip = ip
        self.worker = None

        self.input_field.editingFinished.connect(self.update_ip)
        self.comment_field.editingFinished.connect(self.data_changed.emit)

    def update_ip(self):
        old_ip = self.current_ip
        self.current_ip = self.input_field.text().strip()
        if old_ip != self.current_ip:
            self.data_changed.emit()

    def start_ping(self):
        if self.worker and self.worker.isRunning():
            return

        if not self.current_ip:
            self.indicator.set_status("red")
            self.lbl_delay.setText("Пусто")
            self.lbl_delay.setStyleSheet("color: #EF4444; font-weight: bold;")
            return
            
        self.worker = PingWorker(self.current_ip)
        self.worker.result_ready.connect(self.on_ping_result)
        self.worker.start()

    def on_ping_result(self, ip: str, status: str, delay: float):
        if ip == self.current_ip:
            self.indicator.set_status(status)
            
            if status != "red":
                self.lbl_delay.setText(f"{int(delay)} мс")
                color_hex = "#10B981" if status == "green" else "#F59E0B"
                self.lbl_delay.setStyleSheet(f"color: {color_hex}; font-weight: bold; font-size: 12px;")
            else:
                self.lbl_delay.setText("Down")
                self.lbl_delay.setStyleSheet("color: #EF4444; font-weight: bold; font-size: 12px;")

    def _on_delete_clicked(self):
        self.removed.emit(self)



class ConnectionController(QWidget):
    """Главное координационное окно приложения с современным темным интерфейсом."""
    def __init__(self):
        super().__init__()
        self.setObjectName("MainWindow")
        self.init_ui()
        self.load_config()
        
        # Общий таймер, который каждые 2 секунды заставляет карточки обновлять пинг
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.broadcast_pings)
        self.timer.start(PING_INTERVAL_MS)

    def init_ui(self):
        self.setWindowTitle("Контроль подключения")
        self.resize(580, 500)
        self.setStyleSheet(MODERN_STYLE)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        # Верхняя панель: Заголовок и неоновая кнопка "+"
        header_layout = QHBoxLayout()
        title_label = QLabel("Мониторинг сети")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold; background: transparent;")
        header_layout.addWidget(title_label)
        
        self.btn_add = QPushButton("+")
        self.btn_add.setFixedSize(36, 36)
        self.btn_add.setStyleSheet("""
            QPushButton {
                background-color: #6366F1;
                color: white;
                border: none;
                border-radius: 18px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4F46E5;
            }
            QPushButton:pressed {
                background-color: #3730A3;
            }
        """)
        
        # Добавляем кнопке красивую неоновую тень
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(99, 102, 241, 120))
        shadow.setOffset(0, 4)
        self.btn_add.setGraphicsEffect(shadow)
        
        self.btn_add.clicked.connect(lambda: self.add_ip_row())
        header_layout.addWidget(self.btn_add, alignment=Qt.AlignmentFlag.AlignRight)
        
        self.main_layout.addLayout(header_layout)

        # Прокручиваемая область, где динамически размещаются карточки
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        
        self.scroll_content = QWidget()
        self.list_layout = QVBoxLayout(self.scroll_content)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.list_layout.setContentsMargins(2, 2, 2, 2)
        self.list_layout.setSpacing(10) # Комфортный отступ между карточками
        
        self.scroll.setWidget(self.scroll_content)
        self.main_layout.addWidget(self.scroll)

    def add_ip_row(self, ip="", comment=""):
        row = HostCardWidget(ip, comment)
        row.removed.connect(self.remove_ip_row)
        row.data_changed.connect(self.save_config)
        self.list_layout.addWidget(row)
        
        if not ip:
            row.input_field.setFocus()
        self.save_config()

    def remove_ip_row(self, row: QWidget):
        self.list_layout.removeWidget(row)
        row.deleteLater()
        # Даем виджету время корректно удалиться из памяти перед перезаписью JSON
        QTimer.singleShot(50, self.save_config)

    def broadcast_pings(self):
        """Проходит по всем карточкам в списке и запускает асинхронную проверку связи."""
        for i in range(self.list_layout.count()):
            widget = self.list_layout.itemAt(i).widget()
            if isinstance(widget, HostCardWidget):
                widget.start_ping()

    def save_config(self):
        """Превращает состояние интерфейса в JSON и записывает в файл."""
        data = []
        for i in range(self.list_layout.count()):
            widget = self.list_layout.itemAt(i).widget()
            if isinstance(widget, HostCardWidget):
                data.append({
                    "ip": widget.input_field.text().strip(),
                    "comment": widget.comment_field.text().strip()
                })
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Ошибка сохранения файла конфигурации: {e}")

    def load_config(self):
        """Считывает JSON при запуске приложения и воссоздает карточки."""
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    self.add_ip_row(item.get("ip", ""), item.get("comment", ""))
        except Exception as e:
            print(f"Ошибка загрузки файла конфигурации: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ConnectionController()
    window.show()
    sys.exit(app.exec())

