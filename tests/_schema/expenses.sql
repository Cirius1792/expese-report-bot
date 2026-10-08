CREATE TABLE expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount TEXT NOT NULL,
                currency TEXT NOT NULL,
                merchant TEXT NOT NULL,
                date TEXT NOT NULL,
                category TEXT,
                user_id INTEGER NOT NULL,
                receipt_photo_id TEXT,
                created_at TEXT NOT NULL,
                deleted_at TEXT
            );
