from app import create_app
from app.polling import PollingService
import os

app = create_app()

# Initialize Polling Service
# Only start if not in reloader (or use specific check) to avoid duplicates
# For simplicity in this environment, valid check is usually:
if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or __name__ == '__main__':
    # Actually WERKZEUG_RUN_MAIN is set by the reloader process.
    # We want to run it in the main process if no reloader, or in the reloader process if reloader is on.
    # But be careful of duplicates.
    # Simple approach: Just start it. If debug=True, it might run twice, but that's acceptable for this simple app.
    # Better: Only start if NOT imported (i.e. if __name__ == '__main__') but create_app calls it? No.
    # Let's instantiate and start it here.
    pass

if __name__ == '__main__':
    # Start polling service
    # Make sure we don't start it twice if using reloader
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        polling_service = PollingService(app)
        polling_service.start()
        
    app.run(debug=True, host='0.0.0.0', port=5000)
