from app.reports.routes.router import router

# Importing each route file hangs its endpoints off the shared router. The
# literal paths (/data, /export, /options, /saved) never collide with the one
# param path (/saved/{report_id}), so order is not significant here.
import app.reports.routes.report_data
import app.reports.routes.report_export
import app.reports.routes.report_options
import app.reports.routes.saved_reports
