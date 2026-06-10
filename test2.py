import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import sqlite3
from datetime import datetime


C_SIDEBAR = "#F5C300"      
C_MAIN_BG = "#F4F4F5"      
C_CARD_BG = "#FFFFFF"      
C_ACCENT = "#800000"       
C_ACCENT_HOVER = "#5c0000" 
C_TEXT_DARK = "#1E1F2C"    
C_TEXT_MUTED = "#64748B"   
C_TEXT_LIGHT = "#FFFFFF"   

# --- STATUS COLORS ---
C_AVAILABLE = "#10B981"    
C_SELECTED = "#F5C300"     
C_OCCUPIED = "#800000"     
C_DANGER = "#800000"       


# DATABASE MANAGER

class DatabaseManager:
    def __init__(self, db_name="parking_database.db"):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.setup_database()

    def setup_database(self):
        try:
            self.cursor.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    id_card_number TEXT UNIQUE NOT NULL
                );

                CREATE TABLE IF NOT EXISTS vehicles (
                    vehicle_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    plate_number TEXT UNIQUE NOT NULL,
                    vehicle_type TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS parking_slots (
                    slot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slot_identifier TEXT UNIQUE NOT NULL,
                    category TEXT NOT NULL,
                    status TEXT CHECK(status IN ('Available', 'Occupied')) DEFAULT 'Available'
                );

                CREATE TABLE IF NOT EXISTS parking_sessions (
                    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vehicle_id INTEGER,
                    slot_id INTEGER,
                    entry_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    exit_time DATETIME,
                    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id),
                    FOREIGN KEY (slot_id) REFERENCES parking_slots(slot_id)
                );

                CREATE TABLE IF NOT EXISTS system_users (
                    account_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT CHECK(role IN ('Admin', 'Employee')) NOT NULL
                );
            ''')
            self.conn.commit()

            self.cursor.execute("SELECT COUNT(*) FROM system_users")
            if self.cursor.fetchone()[0] == 0:
                self.cursor.execute("INSERT INTO system_users (username, password, role) VALUES ('admin', 'admin123', 'Admin')")
                self.cursor.execute("INSERT INTO system_users (username, password, role) VALUES ('staff', 'staff123', 'Employee')")
                self.conn.commit()

            self._initialize_slots()

        except sqlite3.Error as e:
            print(f"Database Initialization Error: {e}")

    def _initialize_slots(self):
        self.cursor.execute("SELECT COUNT(*) FROM parking_slots")
        if self.cursor.fetchone()[0] == 0:
            slots_to_insert = []
            for col in ['A', 'B', 'C', 'D']:
                for row in range(1, 9): slots_to_insert.append((f"{col}{row:02d}", "CAR"))
            for col in ['M', 'N', 'O', 'P']:
                for row in range(1, 11): slots_to_insert.append((f"{col}{row:02d}", "BIKE"))
            for col in ['T', 'U', 'V']:
                for row in range(1, 6): slots_to_insert.append((f"{col}{row:02d}", "TRUCK"))

            self.cursor.executemany("INSERT INTO parking_slots (slot_identifier, category) VALUES (?, ?)", slots_to_insert)
            self.conn.commit()

    def verify_login(self, username, password, required_role):
        self.cursor.execute("SELECT role FROM system_users WHERE username=? AND password=?", (username, password))
        result = self.cursor.fetchone()
        if result and result[0] == required_role: return True
        return False

    def get_dashboard_stats(self):
        self.cursor.execute("SELECT COUNT(*) FROM parking_slots")
        total = self.cursor.fetchone()[0]
        self.cursor.execute("SELECT COUNT(*) FROM parking_slots WHERE status='Occupied'")
        occupied = self.cursor.fetchone()[0]
        return total, occupied, total - occupied

    def get_slots_by_category(self, category):
        self.cursor.execute("SELECT slot_identifier, status FROM parking_slots WHERE category=?", (category,))
        return {row[0]: row[1] for row in self.cursor.fetchall()}

    def book_slot(self, slot_id_str, name, id_card, plate, v_type):
        try:
            self.cursor.execute("INSERT OR IGNORE INTO users (full_name, id_card_number) VALUES (?, ?)", (name, id_card))
            self.cursor.execute("SELECT user_id FROM users WHERE id_card_number=?", (id_card,))
            user_id = self.cursor.fetchone()[0]

            self.cursor.execute("INSERT OR IGNORE INTO vehicles (user_id, plate_number, vehicle_type) VALUES (?, ?, ?)", (user_id, plate, v_type))
            self.cursor.execute("SELECT vehicle_id FROM vehicles WHERE plate_number=?", (plate,))
            vehicle_id = self.cursor.fetchone()[0]

            self.cursor.execute("SELECT slot_id FROM parking_slots WHERE slot_identifier=?", (slot_id_str,))
            slot_id = self.cursor.fetchone()[0]
            
            self.cursor.execute("UPDATE parking_slots SET status='Occupied' WHERE slot_id=?", (slot_id,))
            self.cursor.execute("INSERT INTO parking_sessions (vehicle_id, slot_id) VALUES (?, ?)", (vehicle_id, slot_id))
            self.conn.commit()
            return True
        except Exception as e:
            self.conn.rollback()
            return False

    def free_slot(self, slot_id_str):
        self.cursor.execute("SELECT slot_id FROM parking_slots WHERE slot_identifier=?", (slot_id_str,))
        slot_id = self.cursor.fetchone()[0]
        self.cursor.execute("UPDATE parking_slots SET status='Available' WHERE slot_id=?", (slot_id,))
        self.cursor.execute("UPDATE parking_sessions SET exit_time=CURRENT_TIMESTAMP WHERE slot_id=? AND exit_time IS NULL", (slot_id,))
        self.conn.commit()

    def get_history(self, search_term="", category_filter="All"):
        query = '''
            SELECT ps.slot_identifier, u.full_name, v.plate_number, v.vehicle_type, s.entry_time, s.exit_time
            FROM parking_sessions s JOIN vehicles v ON s.vehicle_id = v.vehicle_id
            JOIN users u ON v.user_id = u.user_id JOIN parking_slots ps ON s.slot_id = ps.slot_id WHERE 1=1
        '''
        params = []
        if category_filter != "All":
            query += " AND v.vehicle_type = ?"
            params.append(category_filter)
        if search_term:
            query += " AND (u.full_name LIKE ? OR v.plate_number LIKE ? OR ps.slot_identifier LIKE ?)"
            params.extend([f"%{search_term}%", f"%{search_term}%", f"%{search_term}%"])
        query += " ORDER BY s.entry_time DESC"
        self.cursor.execute(query, params)
        return self.cursor.fetchall()

    def add_system_user(self, username, password, role):
        try:
            self.cursor.execute("INSERT INTO system_users (username, password, role) VALUES (?, ?, ?)", (username, password, role))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False 

    def update_system_user(self, account_id, new_username, new_password, new_role):
        try:
            if new_password.strip() == "":
                self.cursor.execute("UPDATE system_users SET username=?, role=? WHERE account_id=?", (new_username, new_role, account_id))
            else:
                self.cursor.execute("UPDATE system_users SET username=?, password=?, role=? WHERE account_id=?", (new_username, new_password, new_role, account_id))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def add_parking_slot(self, slot_id, category):
        try:
            self.cursor.execute("INSERT INTO parking_slots (slot_identifier, category) VALUES (?, ?)", (slot_id, category.upper()))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False 
            
    def get_system_users(self, search_term="", role_filter="All"):
        query = "SELECT account_id, username, role FROM system_users WHERE 1=1"
        params = []
        if role_filter != "All":
            query += " AND role = ?"
            params.append(role_filter)
        if search_term:
            query += " AND (username LIKE ? OR account_id LIKE ?)"
            params.extend([f"%{search_term}%", f"%{search_term}%"])
        query += " ORDER BY role, username"
        self.cursor.execute(query, params)
        return self.cursor.fetchall()


# --- CUSTOM MODERN WIDGETS ---
class ModernButton(tk.Label):
    def __init__(self, parent, text, bg_color, hover_color, fg_color="white", command=None, font_style=("Helvetica", 12, "bold"), **kwargs):
        super().__init__(parent, text=text, bg=bg_color, fg=fg_color, font=font_style, cursor="hand2", **kwargs)
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.command = command
        self.bind("<Enter>", lambda e: self.config(bg=self.hover_color))
        self.bind("<Leave>", lambda e: self.config(bg=self.bg_color))
        self.bind("<Button-1>", lambda e: self.command() if self.command else None)


# APP CONTROLLER

class ParkingSystemController(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Parking System Manager")
        self.geometry("1200x750") 
        self.configure(bg=C_MAIN_BG)
        
        self.db = DatabaseManager()
        self.current_user_role = None 
        
        self.container = tk.Frame(self)
        self.container.pack(side="top", fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.frames = {}
        for F in (WelcomePage, DashboardPage, AvailableSlotsPage, HistoryPage, AdminSettingsPage):
            page_name = F.__name__
            frame = F(parent=self.container, controller=self)
            self.frames[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame("WelcomePage")

    def show_frame(self, page_name):
        frame = self.frames[page_name]
        if hasattr(frame, 'refresh_data'):
            frame.refresh_data() 
        frame.tkraise()

def build_sidebar(parent_frame, controller, active_page):
    sidebar = tk.Frame(parent_frame, bg=C_SIDEBAR)
    sidebar.grid(row=0, column=0, sticky="nsew")
    
    logo_frame = tk.Frame(sidebar, bg=C_SIDEBAR, pady=40)
    logo_frame.pack(fill="x")
    
    # Updated text colors for visibility on PUP Gold
    tk.Label(logo_frame, text="PARKING", font=("Helvetica", 24, "bold"), fg=C_ACCENT, bg=C_SIDEBAR).pack()
    tk.Label(logo_frame, text="SYSTEM", font=("Helvetica", 24, "bold"), fg=C_TEXT_DARK, bg=C_SIDEBAR).pack()
    
    nav_items = [("Dashboard Overview", "DashboardPage"), ("Available Slots", "AvailableSlotsPage"), ("Parking History", "HistoryPage")]
    
    if controller.current_user_role == "Admin":
        nav_items.append(("System Settings", "AdminSettingsPage"))

    for text, page_name in nav_items:
        if active_page == page_name:
            # Active button (Maroon background, White text)
            btn = tk.Label(sidebar, text=f"  {text}", font=("Helvetica", 13, "bold"), fg=C_TEXT_LIGHT, bg=C_ACCENT, anchor="w", pady=15, padx=20)
        else:
            # Inactive button (Gold background, Obsidian text)
            btn = ModernButton(sidebar, text=f"  {text}", bg_color=C_SIDEBAR, hover_color="#EAB308", fg_color=C_TEXT_DARK, font_style=("Helvetica", 13, "bold"), anchor="w", pady=15, padx=20, command=lambda p=page_name: controller.show_frame(p))
        btn.pack(fill="x", pady=2)

    logout_frame = tk.Frame(sidebar, bg=C_SIDEBAR)
    logout_frame.pack(side="bottom", fill="x", pady=30, padx=20)
    
    # Logout button (Obsidian background, White text)
    ModernButton(logout_frame, text="Logout", bg_color=C_TEXT_DARK, hover_color=C_DANGER, fg_color=C_TEXT_LIGHT, pady=12, command=lambda: controller.show_frame("WelcomePage")).pack(fill="x")
    return sidebar


# 1. WELCOME PAGE

class WelcomePage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=C_CARD_BG)
        self.controller = controller
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1, uniform="equal")
        self.columnconfigure(1, weight=1, uniform="equal")

        self.left_frame = tk.Frame(self, bg=C_SIDEBAR)
        self.left_frame.grid(row=0, column=0, sticky="nsew")
        self.right_frame = tk.Frame(self, bg=C_CARD_BG)
        self.right_frame.grid(row=0, column=1, sticky="nsew")
        
        try:
            self.original_image = Image.open("pup.png")
            self.left_frame.bind("<Configure>", self.resize_image)
            self.img_label = tk.Label(self.left_frame, bg=C_SIDEBAR, bd=0)
            self.img_label.pack(fill="both", expand=True)
        except FileNotFoundError:
            self.original_image = None
            tk.Label(self.left_frame, text="[ Image goes here ]", bg=C_SIDEBAR, fg=C_TEXT_DARK).pack(expand=True)

        self.setup_right_ui()

    def resize_image(self, event):
        if event.width > 0 and event.height > 0 and self.original_image:
            resized_img = self.original_image.resize((event.width, event.height), Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(resized_img)
            self.img_label.config(image=self.photo)

    def setup_right_ui(self):
        ui = tk.Frame(self.right_frame, bg=C_CARD_BG)
        ui.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(ui, text="Smart Parking", font=("Helvetica", 38, "bold"), fg=C_TEXT_DARK, bg=C_CARD_BG).pack()
        tk.Label(ui, text="Management System", font=("Helvetica", 20), fg=C_ACCENT, bg=C_CARD_BG).pack(pady=(0, 40))
        
        ModernButton(ui, text="Employee Portal", bg_color=C_MAIN_BG, hover_color="#E2E8F0", fg_color=C_TEXT_DARK, pady=15, command=lambda: self.open_login_dialog("Employee")).pack(fill="x", pady=10)
        ModernButton(ui, text="Administrator Login", bg_color=C_ACCENT, hover_color=C_ACCENT_HOVER, pady=15, command=lambda: self.open_login_dialog("Admin")).pack(fill="x", pady=10)

    def open_login_dialog(self, role):
        dialog = tk.Toplevel(self)
        dialog.title(f"{role} Login")
        dialog.geometry("350x350")
        dialog.configure(bg=C_CARD_BG)
        dialog.transient(self.controller)
        dialog.focus_force() 
        dialog.grab_set()

        tk.Label(dialog, text=f"{role} Login", font=("Helvetica", 18, "bold"), bg=C_CARD_BG, fg=C_TEXT_DARK).pack(pady=(20, 20))

        tk.Label(dialog, text="Username", font=("Helvetica", 10, "bold"), bg=C_CARD_BG, fg=C_TEXT_MUTED).pack(anchor="w", padx=40)
        username_entry = tk.Entry(dialog, font=("Helvetica", 12), bg="#F1F5F9", relief="flat")
        username_entry.pack(fill="x", padx=40, pady=(5, 15))
        username_entry.focus_set() 

        tk.Label(dialog, text="Password", font=("Helvetica", 10, "bold"), bg=C_CARD_BG, fg=C_TEXT_MUTED).pack(anchor="w", padx=40)
        password_entry = tk.Entry(dialog, font=("Helvetica", 12), bg="#F1F5F9", relief="flat", show="*")
        password_entry.pack(fill="x", padx=40, pady=(5, 20))

        def attempt_login(event=None):
            user = username_entry.get()
            pwd = password_entry.get()
            if self.controller.db.verify_login(user, pwd, role):
                self.controller.current_user_role = role 
                dialog.grab_release() 
                dialog.destroy()
                self.controller.show_frame("DashboardPage")
            else:
                messagebox.showerror("Login Failed", f"Invalid username or password for {role}.", parent=dialog)

        dialog.bind('<Return>', attempt_login)
        ModernButton(dialog, text="Login", bg_color=C_AVAILABLE, hover_color="#059669", pady=10, command=attempt_login).pack(fill="x", padx=40)


# 2. DASHBOARD PAGE

class DashboardPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=C_MAIN_BG)
        self.controller = controller
        self.sidebar_ref = None
        self.setup_ui()
        
    def setup_ui(self):
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=0, minsize=260)
        self.columnconfigure(1, weight=1)
        
        main_frame = tk.Frame(self, bg=C_MAIN_BG)
        main_frame.grid(row=0, column=1, sticky="nsew", padx=50, pady=40)
        tk.Label(main_frame, text="Dashboard Overview", font=("Helvetica", 28, "bold"), fg=C_TEXT_DARK, bg=C_MAIN_BG).pack(anchor="w", pady=(0, 30))
        
        self.cards_frame = tk.Frame(main_frame, bg=C_MAIN_BG)
        self.cards_frame.pack(fill="x", pady=(0, 40))

    def refresh_data(self):
        if self.sidebar_ref: self.sidebar_ref.destroy()
        self.sidebar_ref = build_sidebar(self, self.controller, "DashboardPage")

        for widget in self.cards_frame.winfo_children(): widget.destroy()
        tot, occ, av = self.controller.db.get_dashboard_stats()
        
        def create_card(parent, title, value, color):
            outer = tk.Frame(parent, bg="#E2E8F0", padx=1, pady=1)
            outer.pack(side="left", fill="both", expand=True, padx=(0, 20))
            card = tk.Frame(outer, bg=C_CARD_BG, padx=20, pady=25)
            card.pack(fill="both", expand=True)
            tk.Label(card, text=title, font=("Helvetica", 12), fg=C_TEXT_MUTED, bg=C_CARD_BG).pack(anchor="w")
            tk.Label(card, text=value, font=("Helvetica", 28, "bold"), fg=color, bg=C_CARD_BG).pack(anchor="w", pady=(10, 0))

        create_card(self.cards_frame, "Total Capacity", str(tot), C_TEXT_DARK)
        create_card(self.cards_frame, "Occupied", str(occ), C_ACCENT)
        create_card(self.cards_frame, "Available Spaces", str(av), C_AVAILABLE)


# 3. AVAILABLE SLOTS PAGE 

class AvailableSlotsPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=C_MAIN_BG)
        self.controller = controller
        self.current_tab = "CAR"
        self.selected_slot = None 
        self.sidebar_ref = None
        
        try:
            img = Image.open("car_icon.png").resize((35, 20), Image.Resampling.LANCZOS)
            self.car_icon_img = ImageTk.PhotoImage(img)
        except FileNotFoundError:
            self.car_icon_img = None

        self.setup_ui()

    def setup_ui(self):
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=0, minsize=260)
        self.columnconfigure(1, weight=1)
        
        self.main_frame = tk.Frame(self, bg=C_MAIN_BG)
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        
        top_bar = tk.Frame(self.main_frame, bg=C_MAIN_BG, pady=30, padx=50)
        top_bar.pack(fill="x")
        tk.Label(top_bar, text="Live Parking Map", font=("Helvetica", 28, "bold"), fg=C_TEXT_DARK, bg=C_MAIN_BG).pack(side="left")
        
        self.tabs_frame = tk.Frame(top_bar, bg="#E2E8F0", padx=4, pady=4)
        self.tabs_frame.pack(side="right")
        
        self.btn_car = tk.Button(self.tabs_frame, text="Car", font=("Helvetica", 11, "bold"), relief="flat", bd=0, padx=20, pady=8, command=lambda: self.switch_tab("CAR"))
        self.btn_car.pack(side="left")
        self.btn_bike = tk.Button(self.tabs_frame, text="Bike", font=("Helvetica", 11, "bold"), relief="flat", bd=0, padx=20, pady=8, command=lambda: self.switch_tab("BIKE"))
        self.btn_bike.pack(side="left")
        self.btn_truck = tk.Button(self.tabs_frame, text="Truck", font=("Helvetica", 11, "bold"), relief="flat", bd=0, padx=20, pady=8, command=lambda: self.switch_tab("TRUCK"))
        self.btn_truck.pack(side="left")

        self.grid_container = tk.Frame(self.main_frame, bg=C_MAIN_BG)
        self.grid_container.pack(expand=True, fill="both")
        
        footer = tk.Frame(self.main_frame, bg=C_CARD_BG, pady=20, highlightbackground="#E2E8F0", highlightthickness=1)
        footer.pack(side="bottom", fill="x")
        self.lbl_status = tk.Label(footer, text="Select an available spot to assign a vehicle.", font=("Helvetica", 12), bg=C_CARD_BG, fg=C_TEXT_MUTED)
        self.lbl_status.pack(side="left", padx=50)
        self.btn_confirm = ModernButton(footer, text="Confirm Assignment", bg_color=C_ACCENT, hover_color=C_ACCENT_HOVER, padx=20, pady=10, command=self.open_booking_dialog)
        self.btn_confirm.pack(side="right", padx=50)

    def refresh_data(self):
        if self.sidebar_ref: self.sidebar_ref.destroy()
        self.sidebar_ref = build_sidebar(self, self.controller, "AvailableSlotsPage")
        self.selected_slot = None
        self.update_tab_styles()
        self.render_grid()

    def switch_tab(self, vehicle_type):
        self.current_tab = vehicle_type
        self.refresh_data()

    def update_tab_styles(self):
        for btn in [self.btn_car, self.btn_bike, self.btn_truck]: btn.config(bg="#E2E8F0", fg=C_TEXT_MUTED)
        active_btn = self.btn_car if self.current_tab == "CAR" else self.btn_bike if self.current_tab == "BIKE" else self.btn_truck
        active_btn.config(bg=C_CARD_BG, fg=C_TEXT_DARK)

    def render_grid(self):
        for widget in self.grid_container.winfo_children(): widget.destroy()
        self.parking_data = self.controller.db.get_slots_by_category(self.current_tab)
        
        columns = {}
        for slot_id in self.parking_data.keys():
            col_letter = slot_id[0]
            if col_letter not in columns: columns[col_letter] = []
            columns[col_letter].append(slot_id)
            
        for col in columns: columns[col].sort()

        for col_idx, col_letter in enumerate(sorted(columns.keys())):
            col_frame = tk.Frame(self.grid_container, bg=C_MAIN_BG)
            self.grid_container.columnconfigure(col_idx, weight=1)
            col_frame.grid(row=0, column=col_idx, padx=10, pady=10)
            
            slots = columns[col_letter]
            for i in range(0, len(slots), 2):
                row = i // 2
                if i < len(slots): self.create_interactive_slot(col_frame, slots[i], row, 0)
                tk.Frame(col_frame, bg="#CBD5E1", width=1).grid(row=row, column=1, sticky="ns", padx=8)
                if i + 1 < len(slots): self.create_interactive_slot(col_frame, slots[i+1], row, 2)

    def create_interactive_slot(self, parent, slot_id, row, col):
        state = self.parking_data[slot_id]
        if slot_id == self.selected_slot: state = "selected"

        wrapper = tk.Frame(parent, width=70, height=45)
        wrapper.grid_propagate(False)
        wrapper.pack_propagate(False)
        wrapper.grid(row=row, column=col, padx=4, pady=6)

        bg_color, fg_color, text, img_to_show = C_AVAILABLE, "white", slot_id, None

        if state == "selected": bg_color = C_SELECTED
        elif state == "Occupied":
            bg_color = C_OCCUPIED
            if self.car_icon_img and self.current_tab == "CAR":
                img_to_show = self.car_icon_img
                text = "" 
            else: text = "●"

        lbl = tk.Label(wrapper, text=text, font=("Helvetica", 10, "bold"), bg=bg_color, fg=fg_color, image=img_to_show, cursor="hand2")
        lbl.pack(fill="both", expand=True)
        lbl.bind("<Button-1>", lambda e, s_id=slot_id: self.on_slot_click(s_id))

    def on_slot_click(self, slot_id):
        current_state = self.parking_data[slot_id]
        
        if current_state == "Occupied":
            if messagebox.askyesno("Free Slot", f"Is the vehicle leaving slot {slot_id}?"):
                self.controller.db.free_slot(slot_id)
                self.lbl_status.config(text=f"Slot {slot_id} is now vacant.", fg=C_ACCENT)
        elif current_state == "Available":
            if self.selected_slot == slot_id:
                self.selected_slot = None
                self.lbl_status.config(text="Select an available spot to assign a vehicle.", fg=C_TEXT_MUTED)
            else:
                self.selected_slot = slot_id
                self.lbl_status.config(text=f"Slot {slot_id} selected. Click 'Confirm Assignment' to enter details.", fg=C_TEXT_DARK)
        self.render_grid() 

    def open_booking_dialog(self):
        if not self.selected_slot: return

        dialog = tk.Toplevel(self)
        dialog.title(f"Book Slot {self.selected_slot}")
        dialog.geometry("400x450")
        dialog.configure(bg=C_CARD_BG)
        dialog.transient(self.controller)
        dialog.focus_force()
        dialog.grab_set() 

        tk.Label(dialog, text=f"Assign {self.current_tab}", font=("Helvetica", 18, "bold"), bg=C_CARD_BG, fg=C_TEXT_DARK).pack(pady=(20, 20))

        entries = {}
        for field in ["Full Name", "ID Card Number", "Plate Number"]:
            tk.Label(dialog, text=field, font=("Helvetica", 10, "bold"), bg=C_CARD_BG, fg=C_TEXT_MUTED).pack(anchor="w", padx=40)
            entry = tk.Entry(dialog, font=("Helvetica", 12), bg="#F1F5F9", relief="flat")
            entry.pack(fill="x", padx=40, pady=(5, 15))
            entries[field] = entry

        def save_to_db():
            name = entries["Full Name"].get()
            id_card = entries["ID Card Number"].get()
            plate = entries["Plate Number"].get()

            if not all([name, id_card, plate]):
                messagebox.showerror("Error", "All fields are required.", parent=dialog)
                return

            success = self.controller.db.book_slot(self.selected_slot, name, id_card, plate, self.current_tab)
            if success:
                self.lbl_status.config(text=f"Vehicle assigned to {self.selected_slot} successfully.", fg=C_AVAILABLE)
                self.selected_slot = None
                self.render_grid()
                dialog.destroy()
            else:
                messagebox.showerror("Database Error", "Failed to assign. Please ensure ID and Plate are unique.", parent=dialog)

        ModernButton(dialog, text="Save & Confirm", bg_color=C_ACCENT, hover_color=C_ACCENT_HOVER, pady=10, command=save_to_db).pack(fill="x", padx=40, pady=20)



# 4. HISTORY PAGE

class HistoryPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=C_MAIN_BG)
        self.controller = controller
        self.sidebar_ref = None
        self.current_filter = "All"
        self.search_var = tk.StringVar()
        self.setup_ui()
        
    def setup_ui(self):
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=0, minsize=260)
        self.columnconfigure(1, weight=1)
        
        main_frame = tk.Frame(self, bg=C_MAIN_BG)
        main_frame.grid(row=0, column=1, sticky="nsew", padx=50, pady=40)
        
        header_frame = tk.Frame(main_frame, bg=C_MAIN_BG)
        header_frame.pack(fill="x", pady=(0, 30))
        tk.Label(header_frame, text="Activity Logs", font=("Helvetica", 28, "bold"), fg=C_TEXT_DARK, bg=C_MAIN_BG).pack(side="left")
        
        table_outer = tk.Frame(main_frame, bg="#E2E8F0", padx=1, pady=1)
        table_outer.pack(fill="both", expand=True)
        
        self.table_container = tk.Frame(table_outer, bg=C_CARD_BG)
        self.table_container.pack(fill="both", expand=True)
        
        filter_bar = tk.Frame(self.table_container, bg=C_CARD_BG, padx=25, pady=20)
        filter_bar.pack(fill="x")
        
        search_frame = tk.Frame(filter_bar, bg="#F1F5F9", padx=10, pady=8)
        search_frame.pack(side="left")
        tk.Label(search_frame, text="🔍", bg="#F1F5F9", fg=C_TEXT_MUTED).pack(side="left", padx=(0, 5))
        self.search_entry = tk.Entry(search_frame, textvariable=self.search_var, bg="#F1F5F9", relief="flat", width=25, font=("Helvetica", 11))
        self.search_entry.pack(side="left")
        self.search_entry.bind("<KeyRelease>", lambda e: self.refresh_table()) 
        
        tk.Label(filter_bar, text="Filter:", font=("Helvetica", 11, "bold"), fg=C_TEXT_MUTED, bg=C_CARD_BG).pack(side="left", padx=(30, 10))
        
        self.filter_btns = {}
        for category in ["All", "CAR", "BIKE", "TRUCK"]:
            btn = ModernButton(filter_bar, text=category.capitalize(), bg_color="#F1F5F9", hover_color="#E2E8F0", fg_color=C_TEXT_DARK, font_style=("Helvetica", 10), command=lambda c=category: self.set_filter(c))
            btn.pack(side="left", padx=5)
            self.filter_btns[category] = btn

        self.table_data = tk.Frame(self.table_container, bg=C_CARD_BG, padx=25, pady=10)
        self.table_data.pack(fill="both", expand=True)

    def refresh_data(self):
        if self.sidebar_ref: self.sidebar_ref.destroy()
        self.sidebar_ref = build_sidebar(self, self.controller, "HistoryPage")
        self.refresh_table()
        
    def set_filter(self, category):
        self.current_filter = category
        for key, btn in self.filter_btns.items():
            if key == category:
                btn.config(bg=C_ACCENT, fg="white")
                btn.bg_color = C_ACCENT 
            else:
                btn.config(bg="#F1F5F9", fg=C_TEXT_DARK)
                btn.bg_color = "#F1F5F9"
        self.refresh_table()

    def refresh_table(self):
        for widget in self.table_data.winfo_children(): widget.destroy()

        headers = ["SLOT", "DRIVER NAME", "PLATE", "TYPE", "TIME IN", "TIME OUT"]
        for i, h in enumerate(headers):
            self.table_data.columnconfigure(i, weight=1)
            tk.Label(self.table_data, text=h, font=("Helvetica", 10, "bold"), fg=C_TEXT_MUTED, bg=C_CARD_BG, anchor="w").grid(row=0, column=i, sticky="ew", pady=(0, 15))

        search_term = self.search_var.get()
        logs = self.controller.db.get_history(search_term, self.current_filter)
        
        for row_idx, record in enumerate(logs):
            for col_idx, value in enumerate(record):
                display_val = str(value) if value else "Ongoing"
                if col_idx in [4, 5] and value: 
                    try: display_val = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").strftime("%I:%M %p")
                    except: pass
                tk.Label(self.table_data, text=display_val, font=("Helvetica", 10), fg=C_TEXT_DARK, bg=C_CARD_BG, anchor="w").grid(row=row_idx+1, column=col_idx, sticky="ew", pady=5)


# 5. ADMIN SETTINGS PAGE (TABBED & FILTERED)

class AdminSettingsPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=C_MAIN_BG)
        self.controller = controller
        self.sidebar_ref = None
        self.setup_ui()
        
    def setup_ui(self):
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=0, minsize=260)
        self.columnconfigure(1, weight=1)
        
        main_frame = tk.Frame(self, bg=C_MAIN_BG)
        main_frame.grid(row=0, column=1, sticky="nsew", padx=50, pady=40)
        
        # --- HEADER & TAB NAVIGATION ---
        header_frame = tk.Frame(main_frame, bg=C_MAIN_BG)
        header_frame.pack(fill="x", pady=(0, 20))
        tk.Label(header_frame, text="System Administration", font=("Helvetica", 28, "bold"), fg=C_TEXT_DARK, bg=C_MAIN_BG).pack(side="left")
        
        self.tabs_frame = tk.Frame(header_frame, bg="#E2E8F0", padx=4, pady=4)
        self.tabs_frame.pack(side="right")
        
        self.btn_acc_tab = tk.Button(self.tabs_frame, text="Account Management", font=("Helvetica", 11, "bold"), relief="flat", bd=0, padx=20, pady=8, command=lambda: self.switch_tab("ACCOUNTS"))
        self.btn_acc_tab.pack(side="left")
        
        self.btn_slot_tab = tk.Button(self.tabs_frame, text="Parking Setup", font=("Helvetica", 11, "bold"), relief="flat", bd=0, padx=20, pady=8, command=lambda: self.switch_tab("SLOTS"))
        self.btn_slot_tab.pack(side="left")

        self.content_container = tk.Frame(main_frame, bg=C_MAIN_BG)
        self.content_container.pack(fill="both", expand=True)

        self.current_filter = "All"
        self.search_var = tk.StringVar()

        self.setup_accounts_view()
        self.setup_slots_view()

    def switch_tab(self, tab_name):
        self.current_tab = tab_name
        self.btn_acc_tab.config(bg="#E2E8F0", fg=C_TEXT_MUTED)
        self.btn_slot_tab.config(bg="#E2E8F0", fg=C_TEXT_MUTED)
        
        self.accounts_frame.pack_forget()
        self.slots_frame.pack_forget()

        if tab_name == "ACCOUNTS":
            self.btn_acc_tab.config(bg=C_CARD_BG, fg=C_TEXT_DARK)
            self.accounts_frame.pack(fill="both", expand=True)
            self.refresh_users_list()
        else:
            self.btn_slot_tab.config(bg=C_CARD_BG, fg=C_TEXT_DARK)
            self.slots_frame.pack(fill="both", expand=True)

    def setup_accounts_view(self):
        self.accounts_frame = tk.Frame(self.content_container, bg=C_MAIN_BG)

        # -- HORIZONTAL ADD USER FORM --
        add_card = tk.Frame(self.accounts_frame, bg=C_CARD_BG, padx=20, pady=20, highlightbackground="#E2E8F0", highlightthickness=1)
        add_card.pack(fill="x", pady=(0, 20))
        tk.Label(add_card, text="Register New Account", font=("Helvetica", 14, "bold"), fg=C_TEXT_DARK, bg=C_CARD_BG).pack(anchor="w", pady=(0, 15))

        form_row = tk.Frame(add_card, bg=C_CARD_BG)
        form_row.pack(fill="x")

        tk.Label(form_row, text="Username:", font=("Helvetica", 10, "bold"), fg=C_TEXT_MUTED, bg=C_CARD_BG).pack(side="left", padx=(0, 10))
        u_entry = tk.Entry(form_row, font=("Helvetica", 11), bg="#F1F5F9", relief="flat", width=15)
        u_entry.pack(side="left", padx=(0, 20))

        tk.Label(form_row, text="Password:", font=("Helvetica", 10, "bold"), fg=C_TEXT_MUTED, bg=C_CARD_BG).pack(side="left", padx=(0, 10))
        p_entry = tk.Entry(form_row, font=("Helvetica", 11), bg="#F1F5F9", relief="flat", width=15)
        p_entry.pack(side="left", padx=(0, 20))

        tk.Label(form_row, text="Role:", font=("Helvetica", 10, "bold"), fg=C_TEXT_MUTED, bg=C_CARD_BG).pack(side="left", padx=(0, 10))
        r_combo = ttk.Combobox(form_row, values=["Employee", "Admin"], state="readonly", font=("Helvetica", 11), width=10)
        r_combo.set("Employee")
        r_combo.pack(side="left", padx=(0, 20))

        def submit_user():
            if not u_entry.get() or not p_entry.get():
                messagebox.showerror("Error", "All fields required.")
                return
            if self.controller.db.add_system_user(u_entry.get(), p_entry.get(), r_combo.get()):
                messagebox.showinfo("Success", f"User {u_entry.get()} added successfully!")
                u_entry.delete(0, tk.END); p_entry.delete(0, tk.END)
                self.refresh_users_list()
            else:
                messagebox.showerror("Error", "Username already exists.")

        ModernButton(form_row, text="Create Account", bg_color=C_ACCENT, hover_color=C_ACCENT_HOVER, pady=6, padx=15, command=submit_user).pack(side="left")

        # -- FILTERABLE ACCOUNTS TABLE --
        table_outer = tk.Frame(self.accounts_frame, bg="#E2E8F0", padx=1, pady=1)
        table_outer.pack(fill="both", expand=True)
        self.table_container = tk.Frame(table_outer, bg=C_CARD_BG)
        self.table_container.pack(fill="both", expand=True)

        filter_bar = tk.Frame(self.table_container, bg=C_CARD_BG, padx=25, pady=20)
        filter_bar.pack(fill="x")

        search_frame = tk.Frame(filter_bar, bg="#F1F5F9", padx=10, pady=8)
        search_frame.pack(side="left")
        tk.Label(search_frame, text="🔍", bg="#F1F5F9", fg=C_TEXT_MUTED).pack(side="left", padx=(0, 5))
        self.search_entry = tk.Entry(search_frame, textvariable=self.search_var, bg="#F1F5F9", relief="flat", width=25, font=("Helvetica", 11))
        self.search_entry.pack(side="left")
        self.search_entry.bind("<KeyRelease>", lambda e: self.refresh_users_list())

        tk.Label(filter_bar, text="Filter Role:", font=("Helvetica", 11, "bold"), fg=C_TEXT_MUTED, bg=C_CARD_BG).pack(side="left", padx=(30, 10))
        self.filter_btns = {}
        for role in ["All", "Admin", "Employee"]:
            btn = ModernButton(filter_bar, text=role, bg_color="#F1F5F9", hover_color="#E2E8F0", fg_color=C_TEXT_DARK, font_style=("Helvetica", 10), command=lambda r=role: self.set_filter(r))
            btn.pack(side="left", padx=5)
            self.filter_btns[role] = btn

        self.users_table = tk.Frame(self.table_container, bg=C_CARD_BG, padx=25, pady=10)
        self.users_table.pack(fill="both", expand=True)

    def setup_slots_view(self):
        self.slots_frame = tk.Frame(self.content_container, bg=C_MAIN_BG)

        slot_card = tk.Frame(self.slots_frame, bg=C_CARD_BG, padx=40, pady=40, highlightbackground="#E2E8F0", highlightthickness=1)
        slot_card.pack(anchor="w")

        tk.Label(slot_card, text="Add New Parking Slot", font=("Helvetica", 18, "bold"), fg=C_TEXT_DARK, bg=C_CARD_BG).pack(anchor="w", pady=(0, 20))

        tk.Label(slot_card, text="Slot Identifier (e.g., A09, M15)", font=("Helvetica", 11, "bold"), fg=C_TEXT_MUTED, bg=C_CARD_BG).pack(anchor="w")
        s_entry = tk.Entry(slot_card, font=("Helvetica", 14), bg="#F1F5F9", relief="flat", width=25)
        s_entry.pack(fill="x", pady=(5, 20))

        tk.Label(slot_card, text="Assigned Category", font=("Helvetica", 11, "bold"), fg=C_TEXT_MUTED, bg=C_CARD_BG).pack(anchor="w")
        c_combo = ttk.Combobox(slot_card, values=["CAR", "BIKE", "TRUCK"], state="readonly", font=("Helvetica", 14), width=23)
        c_combo.set("CAR")
        c_combo.pack(fill="x", pady=(5, 30))

        def submit_slot():
            if not s_entry.get():
                messagebox.showerror("Error", "Slot ID is required.")
                return
            if self.controller.db.add_parking_slot(s_entry.get(), c_combo.get()):
                messagebox.showinfo("Success", f"Slot {s_entry.get()} added to map!")
                s_entry.delete(0, tk.END)
            else:
                messagebox.showerror("Error", "Slot ID already exists.")

        ModernButton(slot_card, text="Create Slot & Add to Map", bg_color=C_ACCENT, hover_color=C_ACCENT_HOVER, pady=12, command=submit_slot).pack(fill="x")

    def set_filter(self, role):
        self.current_filter = role
        for key, btn in self.filter_btns.items():
            if key == role:
                btn.config(bg=C_ACCENT, fg="white")
                btn.bg_color = C_ACCENT
            else:
                btn.config(bg="#F1F5F9", fg=C_TEXT_DARK)
                btn.bg_color = "#F1F5F9"
        self.refresh_users_list()

    def refresh_users_list(self):
        for widget in self.users_table.winfo_children(): widget.destroy()

        headers = ["ACCOUNT ID", "USERNAME", "ACCOUNT ROLE", "ACTION"]
        for i, h in enumerate(headers):
            self.users_table.columnconfigure(i, weight=1)
            tk.Label(self.users_table, text=h, font=("Helvetica", 10, "bold"), fg=C_TEXT_MUTED, bg=C_CARD_BG, anchor="w").grid(row=0, column=i, sticky="ew", pady=(0, 10))

        search_term = self.search_var.get()
        users = self.controller.db.get_system_users(search_term, self.current_filter)

        for row_idx, user in enumerate(users):
            account_id, username, role = user
            text_color = C_ACCENT if role == "Admin" else C_TEXT_DARK
            
            tk.Label(self.users_table, text=str(account_id), font=("Helvetica", 11), fg=text_color, bg=C_CARD_BG, anchor="w").grid(row=row_idx+1, column=0, sticky="ew", pady=8)
            tk.Label(self.users_table, text=username, font=("Helvetica", 11), fg=text_color, bg=C_CARD_BG, anchor="w").grid(row=row_idx+1, column=1, sticky="ew", pady=8)
            tk.Label(self.users_table, text=role, font=("Helvetica", 11), fg=text_color, bg=C_CARD_BG, anchor="w").grid(row=row_idx+1, column=2, sticky="ew", pady=8)
            
            edit_btn = ModernButton(self.users_table, text="✎ Edit", bg_color=C_SELECTED, hover_color="#D97706", fg_color="white", font_style=("Helvetica", 9, "bold"), pady=4, padx=15, command=lambda u=account_id, n=username, r=role: self.open_edit_dialog(u, n, r))
            edit_btn.grid(row=row_idx+1, column=3, sticky="w")

    def open_edit_dialog(self, account_id, current_username, current_role):
        dialog = tk.Toplevel(self)
        dialog.title("Edit Account")
        dialog.geometry("350x400")
        dialog.configure(bg=C_CARD_BG)
        dialog.transient(self.controller)
        dialog.focus_force()
        dialog.grab_set()

        tk.Label(dialog, text="Edit Account", font=("Helvetica", 16, "bold"), bg=C_CARD_BG, fg=C_TEXT_DARK).pack(pady=(20, 15))

        tk.Label(dialog, text="Username", font=("Helvetica", 10, "bold"), bg=C_CARD_BG, fg=C_TEXT_MUTED).pack(anchor="w", padx=40)
        u_entry = tk.Entry(dialog, font=("Helvetica", 12), bg="#F1F5F9", relief="flat")
        u_entry.insert(0, current_username) 
        u_entry.pack(fill="x", padx=40, pady=(2, 10))

        tk.Label(dialog, text="New Password (leave blank to keep old)", font=("Helvetica", 10, "bold"), bg=C_CARD_BG, fg=C_TEXT_MUTED).pack(anchor="w", padx=40)
        p_entry = tk.Entry(dialog, font=("Helvetica", 12), bg="#F1F5F9", relief="flat", show="*")
        p_entry.pack(fill="x", padx=40, pady=(2, 10))

        tk.Label(dialog, text="Role", font=("Helvetica", 10, "bold"), bg=C_CARD_BG, fg=C_TEXT_MUTED).pack(anchor="w", padx=40)
        r_combo = ttk.Combobox(dialog, values=["Employee", "Admin"], state="readonly", font=("Helvetica", 12))
        r_combo.set(current_role) 
        r_combo.pack(fill="x", padx=40, pady=(2, 25))

        def submit_update():
            if not u_entry.get():
                messagebox.showerror("Error", "Username cannot be empty.", parent=dialog)
                return
            
            success = self.controller.db.update_system_user(account_id, u_entry.get(), p_entry.get(), r_combo.get())
            if success:
                messagebox.showinfo("Success", "Account successfully updated!", parent=dialog)
                dialog.destroy()
                self.refresh_users_list()
            else:
                messagebox.showerror("Error", "That username is already taken.", parent=dialog)

        ModernButton(dialog, text="Save Changes", bg_color=C_ACCENT, hover_color=C_ACCENT_HOVER, pady=10, command=submit_update).pack(fill="x", padx=40)

    def refresh_data(self):
        if self.sidebar_ref: self.sidebar_ref.destroy()
        self.sidebar_ref = build_sidebar(self, self.controller, "AdminSettingsPage")
        self.switch_tab("ACCOUNTS") 

if __name__ == "__main__":
    app = ParkingSystemController()
    app.mainloop()