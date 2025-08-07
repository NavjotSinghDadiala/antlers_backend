from app import app, scheduler_thread, schedule_weekly_swap_events
import threading

if __name__ == "__main__":
    # Start the scheduler thread if not already running
    if scheduler_thread is None:
        scheduler_thread = threading.Timer(5, schedule_weekly_swap_events)
        scheduler_thread.daemon = True
        scheduler_thread.start()
        
    # Run the app with host binding for external access
    app.run(host='0.0.0.0', port=5000, use_reloader=False, debug=True) 