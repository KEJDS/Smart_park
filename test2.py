import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime, timezone, timedelta

# --- CONFIGURE PHILIPPINE TIME (PHT) ---
PHT = timezone(timedelta(hours=8))

C_SIDEBAR = "#6D0E10"           
C_SIDEBAR_DARK = "#4A090B"      
C_SIDEBAR_ACTIVE = "#FFFFFF"    
C_ACCENT = "#F5C300"            
C_MAIN_BG = "#F8FAFC"           
C_CARD_BG = "#FFFFFF"           
C_BORDER = "#F1F5F9"            
C_TEXT_DARK = "#1E293B"         
C_TEXT_MUTED = "#94A3B8"        
C_TEXT_LIGHT = "#FFFFFF"        
C_AVAILABLE = "#10B981"         
C_DANGER = "#EF4444"            

def get_pht_time():
    """Forces strict Philippine Time (UTC+8)."""
    return (datetime.now(timezone.utc) + timedelta(hours=8))

# DATABASE MANAGER
class DatabaseManager:
    def __init__(self, db_name="parking_database.db"):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.setup_database()

    def setup_database(self):
        try:
            # Added account_id to parking_sessions to link the issuing employee!
            self.cursor.executescript('''
                CREATE TABLE IF NOT EXISTS vehicles (
                    vehicle_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    driver_name TEXT NOT NULL,
                    plate_number TEXT UNIQUE NOT NULL,
                    vehicle_type TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS parking_slots (
                    slot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slot_identifier TEXT UNIQUE NOT NULL,
                    category TEXT NOT NULL,
                    status TEXT CHECK(status IN ('Available', 'Occupied', 'Maintenance')) DEFAULT 'Available'
                );
                CREATE TABLE IF NOT EXISTS system_users (
                    account_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT CHECK(role IN ('Admin', 'Employee')) NOT NULL
                );
                CREATE TABLE IF NOT EXISTS parking_sessions (
                    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vehicle_id INTEGER,
                    slot_id INTEGER,
                    account_id INTEGER, 
                    entry_time TEXT,
                    exit_time TEXT,
                    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id),
                    FOREIGN KEY (slot_id) REFERENCES parking_slots(slot_id),
                    FOREIGN KEY (account_id) REFERENCES system_users(account_id)
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
        self.cursor.execute("SELECT account_id, role FROM system_users WHERE username=? AND password=?", (username, password))
        result = self.cursor.fetchone()
        if result and result[1] == required_role: 
            return result[0] # Return the account_id to track who is logging in
        return False

    def get_dashboard_stats(self):
        self.cursor.execute("SELECT COUNT(*) FROM parking_slots")
        total = self.cursor.fetchone()[0]
        self.cursor.execute("SELECT COUNT(*) FROM parking_slots WHERE status='Occupied'")
        occupied = self.cursor.fetchone()[0]
        self.cursor.execute("SELECT COUNT(*) FROM parking_slots WHERE status='Maintenance'")
        maintenance = self.cursor.fetchone()[0]
        return total, occupied, (total - occupied - maintenance), maintenance

    def get_slots_by_category(self, category):
        self.cursor.execute("SELECT slot_identifier, status FROM parking_slots WHERE category=?", (category,))
        return {row[0]: row[1] for row in self.cursor.fetchall()}

    def set_slot_status(self, slot_id_str, status):
        self.cursor.execute("UPDATE parking_slots SET status=? WHERE slot_identifier=?", (status, slot_id_str))
        self.conn.commit()

    def get_peak_analytics(self):
        self.cursor.execute("SELECT COUNT(*) FROM parking_sessions")
        if self.cursor.fetchone()[0] == 0:
            return "Insufficient Data", "Insufficient Data"
        
        self.cursor.execute("SELECT strftime('%w', entry_time) as dow, COUNT(*) as c FROM parking_sessions GROUP BY dow ORDER BY c DESC LIMIT 1")
        day_res = self.cursor.fetchone()
        days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        peak_day = days[int(day_res[0])] if day_res else "No Data"
        
        self.cursor.execute("SELECT strftime('%H', entry_time) as hr, COUNT(*) as c FROM parking_sessions GROUP BY hr ORDER BY c DESC LIMIT 1")
        hour_res = self.cursor.fetchone()
        if hour_res:
            hr = int(hour_res[0])
            ampm = "PM" if hr >= 12 else "AM"
            display_hr = hr if hr <= 12 else hr - 12
            if display_hr == 0: display_hr = 12
            peak_hour = f"{display_hr}:00 {ampm}"
        else:
            peak_hour = "No Data"
            
        return peak_day, peak_hour

    def get_active_session_by_slot(self, slot_id_str):
        self.cursor.execute('''
            SELECT s.session_id, v.driver_name, v.plate_number 
            FROM parking_sessions s 
            JOIN vehicles v ON s.vehicle_id = v.vehicle_id
            JOIN parking_slots ps ON s.slot_id = ps.slot_id 
            WHERE ps.slot_identifier=? AND s.exit_time IS NULL
        ''', (slot_id_str,))
        return self.cursor.fetchone()

    def update_session_details(self, session_id, name, plate):
        try:
            self.cursor.execute("SELECT vehicle_id FROM parking_sessions WHERE session_id=?", (session_id,))
            vehicle_id = self.cursor.fetchone()[0]
            
            self.cursor.execute("UPDATE vehicles SET driver_name=?, plate_number=? WHERE vehicle_id=?", (name, plate, vehicle_id))
            self.conn.commit()
            return True
        except sqlite3.Error:
            self.conn.rollback()
            return False

    def book_slot(self, slot_id_str, driver_name, plate, v_type, account_id):
        try:
            self.cursor.execute("SELECT vehicle_id FROM vehicles WHERE plate_number=?", (plate,))
            v_res = self.cursor.fetchone()
            if v_res:
                vehicle_id = v_res[0]
                self.cursor.execute("UPDATE vehicles SET driver_name=?, vehicle_type=? WHERE vehicle_id=?", (driver_name, v_type, vehicle_id))
            else:
                self.cursor.execute("INSERT INTO vehicles (driver_name, plate_number, vehicle_type) VALUES (?, ?, ?)", (driver_name, plate, v_type))
                vehicle_id = self.cursor.lastrowid
                
            if driver_name.strip() == "":
                raise ValueError("Driver name cannot be empty.")

            if plate.strip() == "":
                raise ValueError("License plate number cannot be empty.")
            
            if plate.strip() != "":
                self.cursor.execute("SELECT COUNT(*) FROM parking_sessions s JOIN vehicles v ON s.vehicle_id = v.vehicle_id WHERE v.plate_number=? AND s.exit_time IS NULL", (plate,))
                if self.cursor.fetchone()[0] > 0:
                    raise ValueError("This vehicle already has an active parking session.")
            
            self.cursor.execute("SELECT slot_id FROM parking_slots WHERE slot_identifier=?", (slot_id_str,))
            slot_id = self.cursor.fetchone()[0]
            
            pht_now = get_pht_time().strftime("%Y-%m-%d %H:%M:%S")
            
            self.cursor.execute("UPDATE parking_slots SET status='Occupied' WHERE slot_id=?", (slot_id,))
            
            # Save the account_id of the user who booked it!
            self.cursor.execute("INSERT INTO parking_sessions (vehicle_id, slot_id, account_id, entry_time) VALUES (?, ?, ?, ?)", (vehicle_id, slot_id, account_id, pht_now))
            
            session_id = self.cursor.lastrowid
            self.conn.commit()
            return session_id 
        except Exception as e:
            self.conn.rollback()
            print("Booking Error:", e)
            return False
        
    def free_slot(self, slot_id_str):
        self.cursor.execute("SELECT slot_id FROM parking_slots WHERE slot_identifier=?", (slot_id_str,))
        slot_id = self.cursor.fetchone()[0]
        pht_now = get_pht_time().strftime("%Y-%m-%d %H:%M:%S")
        self.cursor.execute("UPDATE parking_slots SET status='Available' WHERE slot_id=?", (slot_id,))
        self.cursor.execute("UPDATE parking_sessions SET exit_time=? WHERE slot_id=? AND exit_time IS NULL", (pht_now, slot_id))
        self.conn.commit()

    def get_history(self, category_filter="All", time_filter="All Time"):
        # We now LEFT JOIN the system_users table to fetch the username of the issuer
        query = '''
            SELECT s.session_id, ps.slot_identifier, v.driver_name, v.plate_number, v.vehicle_type, s.entry_time, s.exit_time, su.username
            FROM parking_sessions s 
            JOIN vehicles v ON s.vehicle_id = v.vehicle_id
            JOIN parking_slots ps ON s.slot_id = ps.slot_id 
            LEFT JOIN system_users su ON s.account_id = su.account_id
            WHERE 1=1
        '''
        params = []
        
        if category_filter != "All":
            query += " AND v.vehicle_type = ?"
            params.append(category_filter)
            
        now = get_pht_time()
        if time_filter == "Today":
            start_date = now.strftime("%Y-%m-%d 00:00:00")
            query += " AND s.entry_time >= ?"
            params.append(start_date)
        elif time_filter == "This Week":
            start_date = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d 00:00:00")
            query += " AND s.entry_time >= ?"
            params.append(start_date)
        elif time_filter == "This Month":
            start_date = now.strftime("%Y-%m-01 00:00:00")
            query += " AND s.entry_time >= ?"
            params.append(start_date)
        elif time_filter == "This Year":
            start_date = now.strftime("%Y-01-01 00:00:00")
            query += " AND s.entry_time >= ?"
            params.append(start_date)
            
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
            
    def get_system_users(self):
        query = "SELECT account_id, username, role FROM system_users ORDER BY role, username"
        self.cursor.execute(query)
        return self.cursor.fetchall()

# CUSTOM WIDGETS & UI HELPERS
class ModernButton(tk.Label):
    def __init__(self, parent, text, bg_color, hover_color, fg_color="white", command=None, font_style=("Segoe UI", 10, "bold"), **kwargs):
        super().__init__(parent, text=text, bg=bg_color, fg=fg_color, font=font_style, cursor="hand2", **kwargs)
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.command = command
        self.bind("<Enter>", lambda e: self.config(bg=self.hover_color))
        self.bind("<Leave>", lambda e: self.config(bg=self.bg_color))
        self.bind("<Button-1>", lambda e: self.command() if self.command else None)

def create_modern_entry(parent, show="", width=25):
    entry = tk.Entry(parent, font=("Segoe UI", 11), bg="#FFFFFF", fg=C_TEXT_DARK, 
                     relief="flat", highlightthickness=1, highlightbackground="#CBD5E1", 
                     highlightcolor=C_SIDEBAR, width=width, show=show)
    return entry

def build_top_header(parent, page_title, breadcrumb):
    header = tk.Frame(parent, bg=C_MAIN_BG)
    header.pack(fill="x", pady=(0, 25))
    left = tk.Frame(header, bg=C_MAIN_BG)
    left.pack(side="left")
    tk.Label(left, text=breadcrumb, font=("Segoe UI", 9), fg=C_TEXT_MUTED, bg=C_MAIN_BG).pack(anchor="w", pady=(0, 5))
    tk.Label(left, text=page_title, font=("Segoe UI", 22, "bold"), fg=C_TEXT_DARK, bg=C_MAIN_BG).pack(anchor="w")
    return header

def create_info_card(parent, title, desc):
    card = tk.Frame(parent, bg=C_CARD_BG, highlightbackground=C_BORDER, highlightthickness=1, padx=25, pady=25)
    tk.Label(card, text=title, font=("Segoe UI", 12, "bold"), fg=C_TEXT_DARK, bg=C_CARD_BG).pack(anchor="w")
    tk.Label(card, text=desc, font=("Segoe UI", 10), fg=C_TEXT_MUTED, bg=C_CARD_BG, wraplength=250, justify="left").pack(anchor="w", pady=(5, 15))
    return card

# APP CONTROLLER
class ParkingSystemController(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PUP | Parking Manager")
        self.geometry("1366x768") 
        self.configure(bg=C_MAIN_BG)
        
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TCombobox", fieldbackground="#FFFFFF", background="#FFFFFF", borderwidth=1, bordercolor="#CBD5E1", arrowsize=12)

        self.db = DatabaseManager()
        
        # State Variables
        self.current_user_name = "Guest"
        self.current_user_role = "None" 
        self.current_account_id = None # Tracks the active user's DB ID
        
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

    def show_invoice_dialog(self, session_id, name, plate, slot, category, entry_time_str=None):
        inv = tk.Toplevel(self)
        inv.title("Parking Invoice")
        inv.geometry("400x520")
        inv.configure(bg=C_CARD_BG)
        inv.transient(self)
        inv.focus_force()
        inv.grab_set()

        tk.Label(inv, text="PUP PARKING RECEIPT", font=("Segoe UI", 18, "bold"), bg=C_CARD_BG, fg=C_SIDEBAR).pack(pady=(30, 5))
        tk.Label(inv, text="Official Entry Ticket", font=("Segoe UI", 10), bg=C_CARD_BG, fg=C_TEXT_MUTED).pack()
        
        tk.Frame(inv, bg=C_BORDER, height=2).pack(fill="x", padx=35, pady=20)
        details = tk.Frame(inv, bg=C_CARD_BG)
        details.pack(fill="both", expand=True, padx=45)

        def add_row(parent, label, value, bold_value=False):
            row = tk.Frame(parent, bg=C_CARD_BG)
            row.pack(fill="x", pady=8)
            tk.Label(row, text=label, font=("Segoe UI", 10), bg=C_CARD_BG, fg=C_TEXT_MUTED).pack(side="left")
            v_font = ("Segoe UI", 11, "bold") if bold_value else ("Segoe UI", 11)
            v_color = C_SIDEBAR if bold_value else C_TEXT_DARK
            tk.Label(row, text=value, font=v_font, bg=C_CARD_BG, fg=v_color).pack(side="right")

        if entry_time_str:
            display_time = datetime.strptime(entry_time_str, "%Y-%m-%d %H:%M:%S").strftime("%B %d, %Y - %I:%M %p")
        else:
            display_time = get_pht_time().strftime("%B %d, %Y - %I:%M %p")
        
        add_row(details, "Invoice No:", f"INV-{session_id:06d}", True)
        add_row(details, "Date/Time:", display_time)
        add_row(details, "Driver Name:", name)
        add_row(details, "License Plate:", plate)
        add_row(details, "Vehicle Type:", category)
        add_row(details, "Allocated Slot:", slot, True)

        tk.Frame(inv, bg=C_BORDER, height=2).pack(fill="x", padx=35, pady=20)
        tk.Label(inv, text="Please keep this ticket visible on your dashboard.", font=("Segoe UI", 9, "italic"), bg=C_CARD_BG, fg=C_TEXT_MUTED).pack()
        ModernButton(inv, text="Print & Close Ticket", bg_color=C_AVAILABLE, hover_color="#059669", pady=12, command=inv.destroy).pack(fill="x", padx=45, pady=20)

def build_sidebar(parent_frame, controller, active_page):
    sidebar = tk.Frame(parent_frame, bg=C_SIDEBAR, width=250)
    sidebar.grid(row=0, column=0, sticky="nsew")
    sidebar.grid_propagate(False) 
    
    logo_frame = tk.Frame(sidebar, bg=C_SIDEBAR, pady=30, padx=20)
    logo_frame.pack(fill="x")
    tk.Label(logo_frame, text="PUP QUEZON CITY", font=("Segoe UI", 12, "bold"), fg=C_TEXT_LIGHT, bg=C_SIDEBAR).pack(anchor="w")
    tk.Label(logo_frame, text="PARKING SYSTEM", font=("Segoe UI", 9), fg="#D1D5DB", bg=C_SIDEBAR).pack(anchor="w", pady=(2, 0))

    nav_items = [
        ("⊞", "Dashboard", "DashboardPage"), 
        ("🚘", "Student/Staff Parking", "AvailableSlotsPage"), 
        ("📊", "Reports", "HistoryPage")
    ]
    
    if controller.current_user_role == "Admin":
        nav_items.append(("⚙", "Settings", "AdminSettingsPage"))

    for icon, text, page_name in nav_items:
        if active_page == page_name:
            item_frame = tk.Frame(sidebar, bg=C_SIDEBAR_ACTIVE)
            item_frame.pack(fill="x", pady=2)
            tk.Frame(item_frame, bg=C_ACCENT, width=4).pack(side="left", fill="y")
            tk.Label(item_frame, text=f"  {icon}   {text}", font=("Segoe UI", 10, "bold"), fg=C_SIDEBAR, bg=C_SIDEBAR_ACTIVE, anchor="w", pady=12, padx=15).pack(fill="x")
        else:
            item_frame = tk.Frame(sidebar, bg=C_SIDEBAR)
            item_frame.pack(fill="x", pady=2)
            btn = ModernButton(item_frame, text=f"  {icon}   {text}", bg_color=C_SIDEBAR, hover_color="#881B1E", fg_color="#E2E8F0", font_style=("Segoe UI", 10), anchor="w", pady=12, padx=20, command=lambda p=page_name: controller.show_frame(p))
            btn.pack(fill="x")

    profile_panel = tk.Frame(sidebar, bg=C_SIDEBAR_DARK, pady=15, padx=15)
    profile_panel.pack(side="bottom", fill="x")
    
    avatar = tk.Label(profile_panel, text=controller.current_user_name[:2].upper(), font=("Segoe UI", 9, "bold"), fg=C_SIDEBAR_DARK, bg="#FFFFFF", width=3, height=1)
    avatar.pack(side="left", padx=(0, 10))
    
    info_frame = tk.Frame(profile_panel, bg=C_SIDEBAR_DARK)
    info_frame.pack(side="left", fill="y")
    tk.Label(info_frame, text=controller.current_user_name, font=("Segoe UI", 9, "bold"), fg=C_TEXT_LIGHT, bg=C_SIDEBAR_DARK, anchor="w").pack(anchor="w")
    tk.Label(info_frame, text=controller.current_user_role.upper(), font=("Segoe UI", 7), fg="#D1D5DB", bg=C_SIDEBAR_DARK, anchor="w").pack(anchor="w")
    
    def confirm_logout():
        if messagebox.askyesno("Logout", "Are you sure you want to logout?"):
            controller.current_account_id = None
            controller.show_frame("WelcomePage")

    logout_btn = tk.Label(profile_panel, text="⮞", font=("Segoe UI", 14), fg="#D1D5DB", bg=C_SIDEBAR_DARK, cursor="hand2")
    logout_btn.pack(side="right")
    logout_btn.bind("<Button-1>", lambda e: confirm_logout())
    logout_btn.bind("<Enter>", lambda e: logout_btn.config(fg=C_ACCENT))
    logout_btn.bind("<Leave>", lambda e: logout_btn.config(fg="#D1D5DB"))

    return sidebar

# 1. WELCOME PAGE
class WelcomePage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=C_MAIN_BG)
        self.controller = controller
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        
        center_box = tk.Frame(self, bg=C_CARD_BG, highlightbackground=C_BORDER, highlightthickness=1, padx=40, pady=50)
        center_box.place(relx=0.5, rely=0.5, anchor="center")
        
        tk.Label(center_box, text="PUP PARKING SYSTEM", font=("Segoe UI", 24, "bold"), fg=C_SIDEBAR, bg=C_CARD_BG).pack(pady=(10, 5))
        tk.Label(center_box, text="System Access Portal", font=("Segoe UI", 12), fg=C_TEXT_MUTED, bg=C_CARD_BG).pack(pady=(0, 40))
        
        ModernButton(center_box, text="Employee Authentication", bg_color="#F1F5F9", hover_color="#E2E8F0", fg_color=C_TEXT_DARK, pady=12, command=lambda: self.open_login_dialog("Employee")).pack(fill="x", pady=8)
        ModernButton(center_box, text="Administrator Login", bg_color=C_SIDEBAR, hover_color="#881B1E", fg_color=C_TEXT_LIGHT, pady=12, command=lambda: self.open_login_dialog("Admin")).pack(fill="x", pady=8)

    def open_login_dialog(self, role):
        dialog = tk.Toplevel(self)
        dialog.title("Authentication")
        dialog.geometry("350x420")
        dialog.configure(bg=C_CARD_BG)
        dialog.transient(self.controller)
        dialog.focus_force() 
        dialog.grab_set()

        tk.Label(dialog, text=f"{role} Login", font=("Segoe UI", 18, "bold"), bg=C_CARD_BG, fg=C_SIDEBAR).pack(pady=(35, 25))

        tk.Label(dialog, text="Username", font=("Segoe UI", 9, "bold"), bg=C_CARD_BG, fg=C_TEXT_MUTED).pack(anchor="w", padx=35)
        username_entry = create_modern_entry(dialog, width=28)
        username_entry.pack(fill="x", padx=35, pady=(5, 15), ipady=4)
        username_entry.focus_set() 

        tk.Label(dialog, text="Password", font=("Segoe UI", 9, "bold"), bg=C_CARD_BG, fg=C_TEXT_MUTED).pack(anchor="w", padx=35)
        password_entry = create_modern_entry(dialog, show="*", width=28)
        password_entry.pack(fill="x", padx=35, pady=(5, 25), ipady=4)

        def attempt_login(event=None):
            user = username_entry.get()
            pwd = password_entry.get()
            
            # Verify login now returns the account ID
            account_id = self.controller.db.verify_login(user, pwd, role)
            
            if account_id:
                self.controller.current_account_id = account_id
                self.controller.current_user_name = user
                self.controller.current_user_role = role 
                dialog.grab_release() 
                dialog.destroy()
                self.controller.show_frame("DashboardPage")
            else:
                messagebox.showerror("Access Denied", "Invalid system credentials specified.", parent=dialog)

        dialog.bind('<Return>', attempt_login)
        ModernButton(dialog, text="Login", bg_color=C_AVAILABLE, hover_color="#059669", pady=10, command=attempt_login).pack(fill="x", padx=35)

# 2. DASHBOARD PAGE
class DashboardPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=C_MAIN_BG)
        self.controller = controller
        self.sidebar_ref = None
        self.setup_ui()
        
    def setup_ui(self):
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=0, minsize=250)
        self.columnconfigure(1, weight=1)
        
        self.main_frame = tk.Frame(self, bg=C_MAIN_BG, padx=40, pady=30)
        self.main_frame.grid(row=0, column=1, sticky="nsew")

    def refresh_data(self):
        if self.sidebar_ref: self.sidebar_ref.destroy()
        self.sidebar_ref = build_sidebar(self, self.controller, "DashboardPage")

        for widget in self.main_frame.winfo_children(): widget.destroy()
        build_top_header(self.main_frame, "Dashboard Overview", "⌂ Dashboard")
        
        tot, occ, av, maint = self.controller.db.get_dashboard_stats()
        
        cards_frame = tk.Frame(self.main_frame, bg=C_MAIN_BG)
        cards_frame.pack(fill="x", pady=20)

        def create_stat_card(parent, title, value, color):
            card = tk.Frame(parent, bg=C_CARD_BG, padx=25, pady=25, highlightbackground=C_BORDER, highlightthickness=1)
            card.pack(side="left", fill="both", expand=True, padx=(0, 12))
            tk.Label(card, text=title, font=("Segoe UI", 9, "bold"), fg=C_TEXT_MUTED, bg=C_CARD_BG).pack(anchor="w")
            tk.Label(card, text=value, font=("Segoe UI", 28, "bold"), fg=color, bg=C_CARD_BG).pack(anchor="w", pady=(10, 0))

        create_stat_card(cards_frame, "TOTAL CAPACITY", str(tot), C_TEXT_DARK)
        create_stat_card(cards_frame, "OCCUPIED SPACES", str(occ), C_SIDEBAR)
        create_stat_card(cards_frame, "AVAILABLE SPACES", str(av), C_AVAILABLE)
        create_stat_card(cards_frame, "MAINTENANCE ISOLATION", str(maint), "#64748B")

        p_day, p_hour = self.controller.db.get_peak_analytics()
        
        tk.Label(self.main_frame, text="PREDICTIVE TRAFFIC INSIGHTS", font=("Segoe UI", 11, "bold"), fg=C_TEXT_DARK, bg=C_MAIN_BG).pack(anchor="w", pady=(20, 10))
        analytics_frame = tk.Frame(self.main_frame, bg=C_MAIN_BG)
        analytics_frame.pack(fill="x")
        
        def create_analytics_card(parent, title, value, icon):
            card = tk.Frame(parent, bg=C_CARD_BG, padx=25, pady=20, highlightbackground=C_BORDER, highlightthickness=1)
            card.pack(side="left", fill="both", expand=True, padx=(0, 15))
            tk.Label(card, text=f"{icon}  {title}", font=("Segoe UI", 10, "bold"), fg=C_TEXT_MUTED, bg=C_CARD_BG).pack(anchor="w")
            tk.Label(card, text=value, font=("Segoe UI", 20, "bold"), fg=C_SIDEBAR, bg=C_CARD_BG).pack(anchor="w", pady=(8, 0))
            
        create_analytics_card(analytics_frame, "BUSIEST OPERATIONAL DAY", p_day, "📅")
        create_analytics_card(analytics_frame, "PEAK TRAFFIC HOUR", p_hour, "⏰")

# 3. AVAILABLE SLOTS PAGE
class AvailableSlotsPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=C_MAIN_BG)
        self.controller = controller
        self.current_tab = "CAR"
        self.selected_slot = None 
        self.sidebar_ref = None
        self.setup_ui()

    def setup_ui(self):
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=0, minsize=250)
        self.columnconfigure(1, weight=1)
        self.main_frame = tk.Frame(self, bg=C_MAIN_BG, padx=40, pady=30)
        self.main_frame.grid(row=0, column=1, sticky="nsew")

    def refresh_data(self):
        if self.sidebar_ref: self.sidebar_ref.destroy()
        self.sidebar_ref = build_sidebar(self, self.controller, "AvailableSlotsPage")
        self.selected_slot = None
        self.build_page()

    def build_page(self):
        for widget in self.main_frame.winfo_children(): widget.destroy()
        build_top_header(self.main_frame, "Student/Staff Parking", "⌂ Dashboard  >  Booking")

        tabs_frame = tk.Frame(self.main_frame, bg=C_MAIN_BG)
        tabs_frame.pack(fill="x", pady=(0, 20))
        
        for v_type in ["CAR", "BIKE", "TRUCK"]:
            bg_col = C_SIDEBAR if self.current_tab == v_type else C_CARD_BG
            fg_col = "white" if self.current_tab == v_type else C_TEXT_DARK
            btn = tk.Button(tabs_frame, text=f"  {v_type} ZONE  ", font=("Segoe UI", 9, "bold"), bg=bg_col, fg=fg_col, relief="flat", bd=1, command=lambda t=v_type: self.switch_tab(t))
            btn.pack(side="left", padx=(0, 10), ipady=5)

        self.grid_container = tk.Frame(self.main_frame, bg=C_CARD_BG, highlightbackground=C_BORDER, highlightthickness=1, padx=20, pady=20)
        self.grid_container.pack(expand=True, fill="both")
        self.render_grid()
        
        footer = tk.Frame(self.main_frame, bg=C_MAIN_BG, pady=20)
        footer.pack(side="bottom", fill="x")
        self.lbl_status = tk.Label(footer, text="Select a slot from the grid above.", font=("Segoe UI", 10), bg=C_MAIN_BG, fg=C_TEXT_MUTED)
        self.lbl_status.pack(side="left")
        
        if self.controller.current_user_role == "Admin" and self.selected_slot:
            def flag_maintenance():
                if messagebox.askyesno("Report Problem", f"Flag slot {self.selected_slot} for Maintenance isolation?"):
                    self.controller.db.set_slot_status(self.selected_slot, "Maintenance")
                    self.selected_slot = None
                    self.build_page()
            ModernButton(footer, text="Flag Maintenance", bg_color="#64748B", hover_color="#475569", padx=15, pady=8, command=flag_maintenance).pack(side="right", padx=(0, 10))
            
        if self.selected_slot:
            ModernButton(footer, text="Assign Slot", bg_color=C_AVAILABLE, hover_color="#059669", padx=25, pady=8, command=self.open_booking_dialog).pack(side="right")

    def switch_tab(self, vehicle_type):
        self.current_tab = vehicle_type
        self.build_page()

    def render_grid(self):
        self.parking_data = self.controller.db.get_slots_by_category(self.current_tab)
        columns = {}
        for slot_id in self.parking_data.keys():
            col_letter = slot_id[0]
            if col_letter not in columns: columns[col_letter] = []
            columns[col_letter].append(slot_id)
        for col in columns: columns[col].sort()

        for col_idx, col_letter in enumerate(sorted(columns.keys())):
            col_frame = tk.Frame(self.grid_container, bg=C_CARD_BG)
            self.grid_container.columnconfigure(col_idx, weight=1)
            col_frame.grid(row=0, column=col_idx, padx=10, pady=10)
            slots = columns[col_letter]
            for i in range(0, len(slots), 2):
                row = i // 2
                if i < len(slots): self.create_interactive_slot(col_frame, slots[i], row, 0)
                tk.Frame(col_frame, bg=C_BORDER, width=1).grid(row=row, column=1, sticky="ns", padx=8)
                if i + 1 < len(slots): self.create_interactive_slot(col_frame, slots[i+1], row, 2)

    def create_interactive_slot(self, parent, slot_id, row, col):
        state = self.parking_data[slot_id]
        wrapper = tk.Frame(parent, width=70, height=40)
        wrapper.grid_propagate(False); wrapper.pack_propagate(False)
        wrapper.grid(row=row, column=col, padx=4, pady=6)

        if slot_id == self.selected_slot: 
            bg_color = C_ACCENT; fg_color = "black"
        elif state == "Occupied": 
            bg_color = C_SIDEBAR; fg_color = "white"
        elif state == "Maintenance":
            bg_color = "#64748B"; fg_color = "white"
        else:
            bg_color = C_BORDER; fg_color = C_TEXT_DARK

        lbl = tk.Label(wrapper, text=slot_id, font=("Segoe UI", 9, "bold"), bg=bg_color, fg=fg_color, cursor="hand2")
        lbl.pack(fill="both", expand=True)
        lbl.bind("<Button-1>", lambda e, s_id=slot_id: self.on_slot_click(s_id))

    def on_slot_click(self, slot_id):
        state = self.parking_data[slot_id]
        if state == "Occupied":
            self.open_occupied_options_dialog(slot_id)
        elif state == "Maintenance":
            if self.controller.current_user_role == "Admin":
                if messagebox.askyesno("Resolve Problem", f"Restore slot {slot_id} back to active rotation?"):
                    self.controller.db.set_slot_status(slot_id, "Available"); self.build_page()
            else: messagebox.showwarning("Locked", f"Slot {slot_id} is isolated for engineering maintenance.")
        else:
            self.selected_slot = slot_id if self.selected_slot != slot_id else None
            self.build_page() 

    def open_occupied_options_dialog(self, slot_id):
        opt = tk.Toplevel(self); opt.title(f"Manage {slot_id}"); opt.geometry("340x220"); opt.configure(bg=C_CARD_BG)
        opt.transient(self.controller); opt.focus_force(); opt.grab_set()

        tk.Label(opt, text=f"Slot Options: {slot_id}", font=("Segoe UI", 14, "bold"), bg=C_CARD_BG, fg=C_TEXT_DARK).pack(pady=20)
        
        def run_edit():
            opt.destroy(); self.open_edit_booking_dialog(slot_id)
            
        def run_vacate():
            opt.destroy()
            if messagebox.askyesno("Vacate", f"Free slot {slot_id}?"):
                self.controller.db.free_slot(slot_id); self.build_page()

        ModernButton(opt, text="📝 Edit Parked Details", bg_color=C_SIDEBAR, hover_color="#881B1E", pady=10, command=run_edit).pack(fill="x", padx=40, pady=5)
        ModernButton(opt, text="🚪 Process Departure (Vacate)", bg_color=C_AVAILABLE, hover_color="#059669", pady=10, command=run_vacate).pack(fill="x", padx=40, pady=5)

    def open_edit_booking_dialog(self, slot_id):
        session = self.controller.db.get_active_session_by_slot(slot_id)
        if not session: return
        session_id, curr_name, curr_plate = session

        dialog = tk.Toplevel(self); dialog.title("Edit Info"); dialog.geometry("350x320"); dialog.configure(bg=C_CARD_BG)
        dialog.transient(self.controller); dialog.focus_force(); dialog.grab_set()

        tk.Label(dialog, text=f"Modify Details: {slot_id}", font=("Segoe UI", 15, "bold"), bg=C_CARD_BG, fg=C_TEXT_DARK).pack(pady=20)
        
        entries = {}
        fields = [("Driver Name", curr_name), ("Plate Number", curr_plate)]
        for label, val in fields:
            tk.Label(dialog, text=label, font=("Segoe UI", 9, "bold"), bg=C_CARD_BG, fg=C_TEXT_MUTED).pack(anchor="w", padx=30)
            entry = create_modern_entry(dialog); entry.insert(0, val); entry.pack(fill="x", padx=30, pady=(5, 15), ipady=4)
            entries[label] = entry

        def save_updates():
            success = self.controller.db.update_session_details(session_id, entries["Driver Name"].get(), entries["Plate Number"].get())
            if success:
                messagebox.showinfo("Success", "Driver registry fields updated successfully.", parent=dialog)
                dialog.destroy(); self.build_page()
            else:
                messagebox.showerror("Conflict Error", "Update blocked. License plate may already exist.", parent=dialog)

        ModernButton(dialog, text="Save Modifications", bg_color=C_AVAILABLE, hover_color="#059669", pady=10, command=save_updates).pack(fill="x", padx=30, pady=10)

    def open_booking_dialog(self):
        if not self.selected_slot: return
        dialog = tk.Toplevel(self); dialog.title("Assign Slot"); dialog.geometry("350x340"); dialog.configure(bg=C_CARD_BG)
        dialog.transient(self.controller); dialog.focus_force(); dialog.grab_set() 

        tk.Label(dialog, text=f"Slot {self.selected_slot}", font=("Segoe UI", 16, "bold"), bg=C_CARD_BG, fg=C_SIDEBAR).pack(pady=(25, 15))

        entries = {}
        for field in ["Driver Name", "Plate Number"]:
            tk.Label(dialog, text=field, font=("Segoe UI", 9, "bold"), bg=C_CARD_BG, fg=C_TEXT_MUTED).pack(anchor="w", padx=30)
            entry = create_modern_entry(dialog)
            entry.pack(fill="x", padx=30, pady=(5, 15), ipady=4)
            entries[field] = entry

        def save_to_db():
            driver_name = entries["Driver Name"].get()
            plate_number = entries["Plate Number"].get()
            
            # Use the tracked current_account_id to log who issued this ticket
            session_id = self.controller.db.book_slot(self.selected_slot, driver_name, plate_number, self.current_tab, self.controller.current_account_id)
            
            if not driver_name.strip() or not plate_number.strip():
                messagebox.showerror("Input Error", "All fields must be filled out.", parent=dialog)
                return
            
            if session_id:
                booked_slot = self.selected_slot; self.selected_slot = None; self.build_page(); dialog.destroy()
                self.controller.show_invoice_dialog(session_id, driver_name, plate_number, booked_slot, self.current_tab)
            else: messagebox.showerror("Booking Error", "This vehicle already has an active parking session.", parent=dialog)
            
        ModernButton(dialog, text="Confirm", bg_color=C_AVAILABLE, hover_color="#059669", pady=10, command=save_to_db).pack(fill="x", padx=30, pady=10)

# 4. HISTORY PAGE 
class HistoryPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=C_MAIN_BG)
        self.controller = controller
        self.sidebar_ref = None
        self.current_cat = "All"
        self.current_time = "All Time"
        self.setup_ui()
        
    def setup_ui(self):
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=0, minsize=250)
        self.columnconfigure(1, weight=1)
        self.main_frame = tk.Frame(self, bg=C_MAIN_BG, padx=40, pady=30)
        self.main_frame.grid(row=0, column=1, sticky="nsew")

    def refresh_data(self):
        if self.sidebar_ref: self.sidebar_ref.destroy()
        self.sidebar_ref = build_sidebar(self, self.controller, "HistoryPage")
        self.build_page()

    def build_page(self):
        for widget in self.main_frame.winfo_children(): widget.destroy()
        build_top_header(self.main_frame, "Reports Archive", "⌂ Dashboard  >  Reports")

        container = tk.Frame(self.main_frame, bg=C_CARD_BG, highlightbackground=C_BORDER, highlightthickness=1)
        container.pack(fill="both", expand=True)

        filter_bar = tk.Frame(container, bg=C_CARD_BG, padx=25, pady=20)
        filter_bar.pack(fill="x")
        
        tk.Label(filter_bar, text="Archive:", font=("Segoe UI", 9, "bold"), fg=C_TEXT_MUTED, bg=C_CARD_BG).pack(side="left", padx=(0, 5))
        time_combo = ttk.Combobox(filter_bar, values=["All Time", "Today", "This Week", "This Month", "This Year"], state="readonly", font=("Segoe UI", 9), width=12)
        time_combo.set(self.current_time)
        time_combo.pack(side="left")
        
        def on_time_select(event):
            self.current_time = time_combo.get()
            self.render_table()
        time_combo.bind("<<ComboboxSelected>>", on_time_select)
        
        tk.Label(filter_bar, text="Type:", font=("Segoe UI", 9, "bold"), fg=C_TEXT_MUTED, bg=C_CARD_BG).pack(side="left", padx=(20, 5))
        for category in ["All", "CAR", "BIKE", "TRUCK"]:
            bg_col = C_SIDEBAR if self.current_cat == category else "#F8FAFC"
            fg_col = "white" if self.current_cat == category else C_TEXT_DARK
            btn = tk.Button(filter_bar, text=category, bg=bg_col, fg=fg_col, relief="flat", bd=0, padx=10, command=lambda c=category: self.set_filter(c))
            btn.pack(side="left", padx=5)

        self.table_data = tk.Frame(container, bg=C_CARD_BG, padx=25, pady=10)
        self.table_data.pack(fill="both", expand=True)
        self.render_table()

    def set_filter(self, category):
        self.current_cat = category
        self.build_page()

    def render_table(self):
        for widget in self.table_data.winfo_children(): 
            widget.destroy()
            
        # Added ISSUER column header
        headers = ["INV", "SLOT", "DRIVER", "PLATE", "TYPE", "TIME IN", "TIME OUT", "ISSUER", "ACTION"]
        for i, h in enumerate(headers): 
            self.table_data.columnconfigure(i, weight=1)
            tk.Label(self.table_data, text=h, font=("Segoe UI", 9, "bold"), fg=C_TEXT_MUTED, bg=C_CARD_BG, anchor="w").grid(row=0, column=i, sticky="ew", pady=(0, 15))

        logs = self.controller.db.get_history(self.current_cat, self.current_time)
        
        for row_idx, record in enumerate(logs):
            # Unpacking the new issuer parameter
            s_id, slot, name, plate, cat, entry_t, exit_t, issuer = record
            
            # Default fallback just in case old data exists
            if not issuer: issuer = "System"
            
            tk.Label(self.table_data, text=f"#{s_id:04d}", font=("Segoe UI", 9), fg=C_TEXT_MUTED, bg=C_CARD_BG, anchor="w").grid(row=row_idx+1, column=0, sticky="ew", pady=8)
            tk.Label(self.table_data, text=slot, font=("Segoe UI", 9, "bold"), fg=C_SIDEBAR, bg=C_CARD_BG, anchor="w").grid(row=row_idx+1, column=1, sticky="ew", pady=8)
            tk.Label(self.table_data, text=name, font=("Segoe UI", 9), fg=C_TEXT_DARK, bg=C_CARD_BG, anchor="w").grid(row=row_idx+1, column=2, sticky="ew", pady=8)
            tk.Label(self.table_data, text=plate, font=("Segoe UI", 9), fg=C_TEXT_DARK, bg=C_CARD_BG, anchor="w").grid(row=row_idx+1, column=3, sticky="ew", pady=8)
            tk.Label(self.table_data, text=cat, font=("Segoe UI", 9), fg=C_TEXT_DARK, bg=C_CARD_BG, anchor="w").grid(row=row_idx+1, column=4, sticky="ew", pady=8)
            
            t_in = datetime.strptime(entry_t, "%Y-%m-%d %H:%M:%S").strftime("%b %d, %I:%M %p") if entry_t else "-"
            t_out = datetime.strptime(exit_t, "%Y-%m-%d %H:%M:%S").strftime("%b %d, %I:%M %p") if exit_t else "Active"
            c_out = C_AVAILABLE if t_out == "Active" else C_TEXT_DARK
            
            tk.Label(self.table_data, text=t_in, font=("Segoe UI", 9), fg=C_TEXT_DARK, bg=C_CARD_BG, anchor="w").grid(row=row_idx+1, column=5, sticky="ew", pady=8)
            tk.Label(self.table_data, text=t_out, font=("Segoe UI", 9), fg=c_out, bg=C_CARD_BG, anchor="w").grid(row=row_idx+1, column=6, sticky="ew", pady=8)
            
            # Displaying the Issuer Data
            tk.Label(self.table_data, text=issuer, font=("Segoe UI", 9, "bold"), fg=C_TEXT_DARK, bg=C_CARD_BG, anchor="w").grid(row=row_idx+1, column=7, sticky="ew", pady=8)
            
            print_btn = ModernButton(self.table_data, text="🖨️ Print", bg_color="#F1F5F9", hover_color="#E2E8F0", fg_color=C_TEXT_DARK, font_style=("Segoe UI", 8, "bold"), pady=4, padx=10, command=lambda id=s_id, n=name, p=plate, s=slot, c=cat, t=entry_t: self.controller.show_invoice_dialog(id, n, p, s, c, t))
            print_btn.grid(row=row_idx+1, column=8, sticky="w")

# 5. ADMIN SETTINGS PAGE
class AdminSettingsPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=C_MAIN_BG)
        self.controller = controller
        self.sidebar_ref = None
        self.setup_ui()
        
    def setup_ui(self):
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=0, minsize=250)
        self.columnconfigure(1, weight=1)
        self.main_frame = tk.Frame(self, bg=C_MAIN_BG, padx=40, pady=30)
        self.main_frame.grid(row=0, column=1, sticky="nsew")

    def refresh_data(self):
        if self.sidebar_ref: self.sidebar_ref.destroy()
        self.sidebar_ref = build_sidebar(self, self.controller, "AdminSettingsPage")
        self.build_page()

    def build_page(self):
        for widget in self.main_frame.winfo_children(): widget.destroy()
        build_top_header(self.main_frame, "System Settings", "⌂ Dashboard  >  Settings")
        
        grid = tk.Frame(self.main_frame, bg=C_MAIN_BG)
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=1, uniform="c"); grid.columnconfigure(1, weight=1, uniform="c"); grid.columnconfigure(2, weight=1, uniform="c")

        c1 = create_info_card(grid, "👥 Accounts", "Manage system access credentials.")
        c1.grid(row=0, column=0, sticky="nsew", padx=10, pady=10); tk.Button(c1, text="Create Account →", font=("Segoe UI", 9, "bold"), fg=C_SIDEBAR, bg=C_CARD_BG, bd=0, command=self.open_add_user).pack(anchor="w", pady=(10,0))
        c2 = create_info_card(grid, "📋 Directory", "View and alter registered personnel directories.")
        c2.grid(row=0, column=1, sticky="nsew", padx=10, pady=10); tk.Button(c2, text="Manage Users →", font=("Segoe UI", 9, "bold"), fg=C_SIDEBAR, bg=C_CARD_BG, bd=0, command=self.open_user_table).pack(anchor="w", pady=(10,0))
        c3 = create_info_card(grid, "🚘 Grid Setup", "Append new parking block identifiers.")
        c3.grid(row=0, column=2, sticky="nsew", padx=10, pady=10); tk.Button(c3, text="Add Slot →", font=("Segoe UI", 9, "bold"), fg=C_SIDEBAR, bg=C_CARD_BG, bd=0, command=self.open_add_slot).pack(anchor="w", pady=(10,0))

    def open_add_user(self):
        d = tk.Toplevel(self); d.title("Create Account"); d.geometry("350x400"); d.configure(bg=C_CARD_BG); d.transient(self.controller); d.focus_force(); d.grab_set()
        tk.Label(d, text="New Account", font=("Segoe UI", 16, "bold"), bg=C_CARD_BG, fg=C_TEXT_DARK).pack(pady=20)
        u_entry, p_entry = create_modern_entry(d), create_modern_entry(d)
        tk.Label(d, text="Username", font=("Segoe UI", 9, "bold"), bg=C_CARD_BG, fg=C_TEXT_MUTED).pack(anchor="w", padx=30); u_entry.pack(fill="x", padx=30, pady=5)
        tk.Label(d, text="Password", font=("Segoe UI", 9, "bold"), bg=C_CARD_BG, fg=C_TEXT_MUTED).pack(anchor="w", padx=30); p_entry.pack(fill="x", padx=30, pady=5)
        r_combo = ttk.Combobox(d, values=["Employee", "Admin"], state="readonly", font=("Segoe UI", 11)); r_combo.set("Employee"); r_combo.pack(fill="x", padx=30, pady=15)
        def save():
            if self.controller.db.add_system_user(u_entry.get(), p_entry.get(), r_combo.get()): messagebox.showinfo("Success", "User added.", parent=d); d.destroy()
        ModernButton(d, text="Create", bg_color=C_SIDEBAR, hover_color="#881B1E", pady=8, command=save).pack(fill="x", padx=30, pady=10)

    def open_add_slot(self):
        d = tk.Toplevel(self); d.title("Add Slot"); d.geometry("350x300"); d.configure(bg=C_CARD_BG); d.transient(self.controller); d.focus_force(); d.grab_set()
        tk.Label(d, text="Add Slot", font=("Segoe UI", 16, "bold"), bg=C_CARD_BG, fg=C_TEXT_DARK).pack(pady=20)
        s_entry = create_modern_entry(d)
        tk.Label(d, text="Slot ID", font=("Segoe UI", 9, "bold"), bg=C_CARD_BG, fg=C_TEXT_MUTED).pack(anchor="w", padx=30); s_entry.pack(fill="x", padx=30, pady=5)
        c_combo = ttk.Combobox(d, values=["CAR", "BIKE", "TRUCK"], state="readonly", font=("Segoe UI", 11)); c_combo.set("CAR"); c_combo.pack(fill="x", padx=30, pady=15)
        def save():
            if self.controller.db.add_parking_slot(s_entry.get(), c_combo.get()): messagebox.showinfo("Success", "Slot added.", parent=d); d.destroy()
        ModernButton(d, text="Create", bg_color=C_SIDEBAR, hover_color="#881B1E", pady=8, command=save).pack(fill="x", padx=30, pady=10)

    def open_user_table(self):
        d = tk.Toplevel(self); d.title("Directory"); d.geometry("650x450"); d.configure(bg=C_CARD_BG); d.transient(self.controller); d.focus_force(); d.grab_set()
        tk.Label(d, text="System Accounts", font=("Segoe UI", 16, "bold"), bg=C_CARD_BG, fg=C_TEXT_DARK).pack(pady=20)
        table = tk.Frame(d, bg=C_CARD_BG, padx=25); table.pack(fill="both", expand=True)
        headers = ["ACCOUNT ID", "USERNAME", "ROLE FLAGS", "ACTIONS"]
        for i, h in enumerate(headers): table.columnconfigure(i, weight=1); tk.Label(table, text=h, font=("Segoe UI", 9, "bold"), bg=C_CARD_BG, fg=C_TEXT_MUTED).grid(row=0, column=i, sticky="w", pady=(0, 10))
        
        for row_idx, (aid, user, role) in enumerate(self.controller.db.get_system_users()):
            tk.Label(table, text=f"#{aid:03d}", font=("Segoe UI", 10), bg=C_CARD_BG, fg=C_TEXT_MUTED).grid(row=row_idx+1, column=0, sticky="w", pady=5)
            tk.Label(table, text=user, font=("Segoe UI", 10, "bold"), bg=C_CARD_BG, fg=C_SIDEBAR).grid(row=row_idx+1, column=1, sticky="w", pady=5)
            tk.Label(table, text=role, font=("Segoe UI", 10), bg=C_CARD_BG, fg=C_TEXT_DARK).grid(row=row_idx+1, column=2, sticky="w", pady=5)
            
            action_btn = tk.Button(table, text=" ✎ Alter Records ", font=("Segoe UI", 8, "bold"), bg="#F1F5F9", fg=C_TEXT_DARK, relief="flat", activebackground="#CBD5E1", cursor="hand2",
                                   command=lambda a=aid, u=user, r=role: [d.destroy(), self.open_edit_dialog(a, u, r)])
            action_btn.grid(row=row_idx+1, column=3, sticky="w", pady=5)

    def open_edit_dialog(self, account_id, current_username, current_role):
        dialog = tk.Toplevel(self); dialog.title("Edit Account Settings"); dialog.geometry("400x480"); dialog.configure(bg=C_CARD_BG)
        dialog.transient(self.controller); dialog.focus_force(); dialog.grab_set()

        tk.Label(dialog, text="Modify Directory Profile", font=("Helvetica", 18, "bold"), bg=C_CARD_BG, fg=C_TEXT_DARK).pack(pady=(30, 25))
        tk.Label(dialog, text="Username", font=("Helvetica", 10, "bold"), bg=C_CARD_BG, fg=C_TEXT_MUTED).pack(anchor="w", padx=45)
        u_entry = create_modern_entry(dialog); u_entry.insert(0, current_username); u_entry.pack(fill="x", padx=45, pady=(5, 20), ipady=5)

        tk.Label(dialog, text="New Password (Leave blank to keep old)", font=("Helvetica", 10, "bold"), bg=C_CARD_BG, fg=C_TEXT_MUTED).pack(anchor="w", padx=45)
        p_entry = create_modern_entry(dialog, show="*"); p_entry.pack(fill="x", padx=45, pady=(5, 20), ipady=5)

        tk.Label(dialog, text="Access Role", font=("Helvetica", 10, "bold"), bg=C_CARD_BG, fg=C_TEXT_MUTED).pack(anchor="w", padx=45)
        r_combo = ttk.Combobox(dialog, values=["Employee", "Admin"], state="readonly", font=("Helvetica", 13)); r_combo.set(current_role); r_combo.pack(fill="x", padx=45, pady=(5, 30))

        def submit_update():
            if not u_entry.get():
                messagebox.showerror("Error", "Username object cannot accept null parameters.", parent=dialog); return
            if self.controller.db.update_system_user(account_id, u_entry.get(), p_entry.get(), r_combo.get()):
                messagebox.showinfo("Success", "Account variables compiled and written to database index.", parent=dialog)
                dialog.destroy(); self.build_page()
            else: messagebox.showerror("Fault", "Username identity collision. That identifier is already taken.", parent=dialog)

        ModernButton(dialog, text="Write Profile Alterations", bg_color=C_SIDEBAR, hover_color="#881B1E", pady=12, command=submit_update).pack(fill="x", padx=45)

if __name__ == "__main__":
    app = ParkingSystemController()
    app.mainloop()


C_MAIN_BG         
