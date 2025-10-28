import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

# =====================================================
# Database setup
# =====================================================
def get_connection():
    return sqlite3.connect("library.db", check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()

    # --- Tables ---
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'member'
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT,
            category TEXT,
            total_copies INTEGER DEFAULT 1,
            available_copies INTEGER DEFAULT 1,
            UNIQUE(title, author, category)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS borrow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            book_id INTEGER,
            borrowed_date TEXT,
            due_date TEXT,
            status TEXT DEFAULT 'Pending',
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(book_id) REFERENCES books(id)
        )
    """)

    # --- Default admin ---
    c.execute("SELECT * FROM users WHERE username=?", ("Vikrant Jadhav",))
    if not c.fetchone():
        c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                  ("Vikrant Jadhav", "admin123", "admin"))
    conn.commit()
    conn.close()

# =====================================================
# Utility functions
# =====================================================
def add_user(username, password, role="member"):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (username, password, role))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def login_user(username, password):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
    data = c.fetchone()
    conn.close()
    return data

def add_book(title, author, category, total_copies):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO books (title, author, category, total_copies, available_copies)
            VALUES (?, ?, ?, ?, ?)
        """, (title.strip(), author.strip(), category.strip(), total_copies, total_copies))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # Duplicate book
    finally:
        conn.close()

def edit_book(book_id, title, author, category, total_copies):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT total_copies, available_copies FROM books WHERE id=?", (book_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False
    old_total, old_available = row
    diff = total_copies - old_total
    new_available = max(0, old_available + diff)
    try:
        c.execute("""
            UPDATE books SET title=?, author=?, category=?, total_copies=?, available_copies=?
            WHERE id=?
        """, (title, author, category, total_copies, new_available, book_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_book(book_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM books WHERE id=?", (book_id,))
    conn.commit()
    conn.close()

def get_all_books(search=""):
    conn = get_connection()
    df = pd.read_sql("""
        SELECT id, title, author, category, total_copies, available_copies
        FROM books
        WHERE title LIKE ? OR author LIKE ? OR category LIKE ?
    """, conn, params=(f"%{search}%", f"%{search}%", f"%{search}%"))
    conn.close()
    return df

def request_borrow(user_id, book_id):
    conn = get_connection()
    c = conn.cursor()
    # Check if already pending or borrowed
    c.execute("""
        SELECT * FROM borrow WHERE user_id=? AND book_id=? AND status IN ('Pending', 'Borrowed')
    """, (user_id, book_id))
    if c.fetchone():
        conn.close()
        return False  # Already requested
    borrowed_date = datetime.now().strftime("%Y-%m-%d")
    due_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
    c.execute("""
        INSERT INTO borrow (user_id, book_id, borrowed_date, due_date)
        VALUES (?, ?, ?, ?)
    """, (user_id, book_id, borrowed_date, due_date))
    conn.commit()
    conn.close()
    return True

def approve_request(borrow_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT book_id, status FROM borrow WHERE id=?", (borrow_id,))
    row = c.fetchone()
    if row and row[1] == "Pending":
        book_id = row[0]
        c.execute("SELECT available_copies FROM books WHERE id=?", (book_id,))
        available = c.fetchone()[0]
        if available > 0:
            c.execute("UPDATE borrow SET status='Borrowed' WHERE id=?", (borrow_id,))
            c.execute("UPDATE books SET available_copies=available_copies-1 WHERE id=?", (book_id,))
            conn.commit()
            conn.close()
            return True
    conn.close()
    return False

def reject_request(borrow_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE borrow SET status='Rejected' WHERE id=?", (borrow_id,))
    conn.commit()
    conn.close()

def mark_returned(borrow_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT book_id, status FROM borrow WHERE id=?", (borrow_id,))
    row = c.fetchone()
    if row and row[1] == "Borrowed":
        book_id = row[0]
        c.execute("UPDATE borrow SET status='Returned' WHERE id=?", (borrow_id,))
        c.execute("UPDATE books SET available_copies=available_copies+1 WHERE id=?", (book_id,))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def get_user_requests(user_id):
    conn = get_connection()
    df = pd.read_sql(f"""
        SELECT br.id AS request_id,
               bk.id AS book_id,
               bk.title,
               bk.author,
               br.borrowed_date,
               br.due_date,
               br.status
        FROM borrow br
        JOIN books bk ON br.book_id = bk.id
        WHERE br.user_id = {user_id}
        ORDER BY br.id DESC
    """, conn)
    conn.close()
    return df

def get_all_requests():
    conn = get_connection()
    df = pd.read_sql("""
        SELECT br.id AS request_id,
               u.username AS member,
               bk.title,
               bk.author,
               br.borrowed_date,
               br.due_date,
               br.status
        FROM borrow br
        JOIN books bk ON br.book_id = bk.id
        JOIN users u ON br.user_id = u.id
        ORDER BY br.id DESC
    """, conn)
    conn.close()
    return df

# =====================================================
# Streamlit UI
# =====================================================
st.set_page_config(page_title="📚 Library System", layout="centered")
init_db()

# --- CSS ---
st.markdown("""
<style>
* {font-family:'Helvetica Neue',sans-serif;}
.stButton>button {background-color:#4CAF50;color:white;border:none;padding:10px 24px;border-radius:8px;font-size:16px;}
.stButton>button:hover {background-color:#45a049;}
.title{text-align:center;color:#2c3e50;}
.subtitle{text-align:center;color:#6c757d;font-size:15px;}
.status-pending{background-color:orange;color:white;padding:4px 8px;border-radius:4px;}
.status-borrowed{background-color:green;color:white;padding:4px 8px;border-radius:4px;}
.status-returned{background-color:blue;color:white;padding:4px 8px;border-radius:4px;}
.status-rejected{background-color:red;color:white;padding:4px 8px;border-radius:4px;}
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 class='title'>📚 महर्षी वेद व्यास सार्वजनिक ग्रंथालय, खानापूर, ता. वाई, जि. सातारा </h1>", unsafe_allow_html=True)
#st.markdown("<p class='subtitle'>Streamlit + SQLite | Admin & Member Portal</p>", unsafe_allow_html=True)

if "user" not in st.session_state:
    st.session_state.user = None

# Auto redirect
if st.session_state.user:
    default_menu = "Dashboard"
else:
    default_menu = "Login"

menu = ["Login", "Register", "Dashboard"]
choice = st.sidebar.selectbox("📖 Menu", menu, index=menu.index(default_menu))

# =====================================================
# LOGIN
# =====================================================
if choice == "Login" and not st.session_state.user:
    st.subheader("🔐 Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        user = login_user(username, password)
        if user:
            st.session_state.user = {"id": user[0], "username": user[1], "role": user[3]}
            st.success(f"Welcome {user[1]}! Redirecting to dashboard...")
            st.rerun()
        else:
            st.error("Invalid username or password")

# =====================================================
# REGISTER
# =====================================================
elif choice == "Register" and not st.session_state.user:
    st.subheader("🧾 Register New Member")
    username = st.text_input("Choose Username")
    password = st.text_input("Choose Password", type="password")
    if st.button("Register"):
        if add_user(username, password):
            user = login_user(username, password)
            st.session_state.user = {"id": user[0], "username": user[1], "role": user[3]}
            st.success("🎉 Account created! Redirecting to dashboard...")
            st.rerun()
        else:
            st.error("Username already exists.")

# =====================================================
# DASHBOARD
# =====================================================
elif choice == "Dashboard":
    if not st.session_state.user:
        st.warning("⚠️ Please login first.")
    else:
        user = st.session_state.user
        st.sidebar.markdown(f"👤 **{user['username']} ({user['role']})**")
        if st.sidebar.button("🚪 Logout"):
            st.session_state.user = None
            st.rerun()

        if user["role"] == "admin":
            tab1, tab2, tab3 = st.tabs(["📚 Books", "📘 Borrow Requests", "➕ Add Book"])
        else:
            tab1, tab2 = st.tabs(["📚 Books", "📘 My Requests"])

        # --- BOOKS TAB ---
        with tab1:
            st.subheader("📚 Books")
            search = st.text_input("🔍 Search by title, author, or category")
            books = get_all_books(search)
            st.dataframe(books, use_container_width=True)

            if user["role"] == "admin":
                st.markdown("### Edit/Delete Book")
                book_id = st.number_input("Enter Book ID to Edit/Delete", min_value=1, step=1)
                new_title = st.text_input("New Title")
                new_author = st.text_input("New Author")
                new_category = st.text_input("New Category")
                new_total = st.number_input("New Total Copies", min_value=1, value=1)
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Edit Book"):
                        if edit_book(book_id, new_title, new_author, new_category, new_total):
                            st.success("✅ Book updated successfully!")
                            st.rerun()
                        else:
                            st.error("Error: duplicate or invalid book ID.")
                with col2:
                    if st.button("Delete Book"):
                        delete_book(book_id)
                        st.success("🗑️ Book deleted successfully!")
                        st.rerun()

            if user["role"] == "member":
                st.markdown("### Request Borrow Book")
                book_id = st.number_input("Enter Book ID to Request Borrow", min_value=1, step=1)
                if st.button("Request Borrow"):
                    success = request_borrow(user["id"], book_id)
                    if success:
                        st.success("📥 Borrow request sent! Waiting for admin approval.")
                        st.rerun()
                    else:
                        st.warning("⚠️ You already have a pending or borrowed request for this book.")

        # --- MEMBER REQUEST TAB ---
        if user["role"] == "member":
            with tab2:
                st.subheader("📘 My Borrow Requests")
                requests = get_user_requests(user["id"])
                def color_status(status):
                    return f"<span class='status-{status.lower()}'>{status}</span>"
                if not requests.empty:
                    requests_display = requests.copy()
                    requests_display["Status"] = requests_display["status"].apply(lambda x: color_status(x))
                    requests_display = requests_display.drop(columns=["status"])
                    st.write(requests_display.to_html(escape=False, index=False), unsafe_allow_html=True)

                    st.markdown("### Return Book")
                    borrow_ids = requests[requests['status'] == 'Borrowed']['request_id'].tolist()
                    if borrow_ids:
                        return_id = st.selectbox("Select Book to Return", borrow_ids)
                        if st.button("Return Book"):
                            if mark_returned(return_id):
                                st.success("📗 Book returned successfully!")
                                st.rerun()
                else:
                    st.info("No borrow requests yet.")

        # --- ADMIN REQUEST TAB ---
        if user["role"] == "admin":
            with tab2:
                st.subheader("📘 All Borrow Requests")
                requests = get_all_requests()
                if not requests.empty:
                    def color_status(status):
                        return f"<span class='status-{status.lower()}'>{status}</span>"
                    requests_display = requests.copy()
                    requests_display["Status"] = requests_display["status"].apply(lambda x: color_status(x))
                    requests_display = requests_display.drop(columns=["status"])
                    st.write(requests_display.to_html(escape=False, index=False), unsafe_allow_html=True)

                    st.markdown("### Approve/Reject Requests")
                    borrow_ids = requests[requests['status'] == 'Pending']['request_id'].tolist()
                    if borrow_ids:
                        selected_id = st.selectbox("Select Request ID", borrow_ids)
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("Approve Request"):
                                if approve_request(selected_id):
                                    st.success("✅ Request approved and book borrowed!")
                                    st.rerun()
                                else:
                                    st.error("No available copies!")
                        with col2:
                            if st.button("Reject Request"):
                                reject_request(selected_id)
                                st.success("❌ Request rejected!")
                                st.rerun()

        # --- ADD BOOK TAB ---
        if user["role"] == "admin":
            with tab3:
                st.subheader("➕ Add New Book")
                title = st.text_input("Title")
                author = st.text_input("Author")
                category = st.text_input("Category")
                total_copies = st.number_input("Total Copies", min_value=1, value=1)
                if st.button("Add Book"):
                    if add_book(title, author, category, total_copies):
                        st.success("✅ Book added successfully!")
                        st.rerun()
                    else:
                        st.error("Book already exists.")
