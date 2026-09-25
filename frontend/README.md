# Frontend

The static client is served from the Flask app. Follow the root [project setup](../README.md#clean-setup-windows-powershell), then open `http://127.0.0.1:5000`.

The UI uses HTML, CSS, vanilla JavaScript, Bootstrap 5, and Chart.js. Bootstrap and Chart.js load from jsDelivr and need internet access. The project category form uses a category ID because no category catalog API is exposed. Payment actions update the demo ledger and do not transfer money.
