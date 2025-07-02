from app import app, scheduler_thread, schedule_weekly_swap_events
import threading

if __name__ == "__main__":
    # Start the scheduler thread if not already running
    if scheduler_thread is None:
        scheduler_thread = threading.Timer(5, schedule_weekly_swap_events)
        scheduler_thread.daemon = True
        scheduler_thread.start()
        
    app.run(use_reloader=False) # Disable reloader to prevent duplicate scheduler threads 