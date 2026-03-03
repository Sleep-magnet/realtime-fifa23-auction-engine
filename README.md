# Real-Time Auction Engine ⚡

A high-performance, real-time multiplayer bidding platform designed for synchronized sports roster drafts and live virtual auctions. Built with Flask, Socket.IO, and SQLite, this engine supports concurrent bidding across multiple active rooms with sub-second state synchronization.

![Auction Interface Preview](https://via.placeholder.com/800x400.png?text=Premium+Real-Time+UI)

## 🚀 Key Features

*   **Real-Time WebSockets:** Replaced legacy HTTP polling with Flask-SocketIO to achieve instantaneous, bidirectional communication. Bids, folds, and timer updates are broadcast to all connected clients in milliseconds.
*   **Multiplayer Rooms:** Robust room-based architecture allows for multiple isolated auctions to run concurrently without state bleed.
*   **Synchronized State Management:** Employs SQLite alongside server-authoritative logic to prevent race conditions during high-frequency bidding wars.
*   **Sudden Death Mechanics:** Automated anti-snipe logic dynamically adjusts the countdown timer during late-stage bidding.
*   **Premium Glassmorphic UI:** Features a heavily stylized, responsive frontend built with Tailwind CSS, custom CSS animations (including a 3D pitch grid), and floating reaction emojis.
*   **Live Commentary & Audio:** Implements browser-based speech synthesis (`SpeechSynthesisUtterance`) for automated auctioneer commentary and custom SFX.

## 🛠️ Technology Stack

**Backend:**
*   Python 3.x
*   Flask (Web Framework)
*   Flask-SocketIO / Eventlet (WebSocket Server)
*   SQLite (Database)
*   Pandas (Data Initialization & Processing)

**Frontend:**
*   HTML5 / Canvas
*   Tailwind CSS (Styling)
*   Vanilla JavaScript (DOM Manipulation & Socket Client)
*   Socket.IO (Client)

## ⚡ Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/yourusername/realtime-auction-engine.git
    cd realtime-auction-engine
    ```

2.  **Set up a virtual environment (Recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install flask flask-socketio eventlet pandas
    ```

4.  **Initialize the Database:**
    *Ensure you have the required seed data (e.g., `fifa23.xlsx` and squad CSVs).*
    ```bash
    python update_db.py
    ```

5.  **Run the Server:**
    ```bash
    python app.py
    ```

6.  **Access the Application:**
    Navigate to `http://localhost:5000` in your browser. Open multiple windows/tabs to test the real-time WebSocket broadcasting!

## 🏗️ Architecture Highlights

*   **Server-Authoritative Timer:** To prevent client-side manipulation and ensure sync, the timer source-of-truth remains on the server, while clients handle UI interpolation for smooth progress bars.
*   **Concurrent Safety:** Bidding logic utilizes strict server-side validation against the `current_bid` to reject overlapping/stale requests seamlessly.

## 🤝 Contributing
Contributions, issues, and feature requests are welcome!

## 📝 License
This project is open-source and available under the [MIT License](LICENSE).
