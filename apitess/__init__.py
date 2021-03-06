"""Tesserae API implementation"""
import flask
from flask_cors import CORS

import tesserae.db


def _load_config(app, test_config):
    """Load configuration into `app`"""
    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)


def _register_before_request(app, jobqueue, ingest_queue):
    """Make database and searcher available to app

    From this point forward, before_request exposes access to the database via
    g.db and to the searcher via g.searcher.
    """
    # http://librelist.com/browser/flask/2013/8/21/flask-pymongo-and-blueprint/#811dd1b119757bc09d28425a5bda86d9
    db = tesserae.db.TessMongoConnection(app.config['MONGO_HOSTNAME'],
                                         app.config['MONGO_PORT'],
                                         app.config['MONGO_USER'],
                                         app.config['MONGO_PASSWORD'],
                                         db=app.config['DB_NAME'])

    @app.before_request
    def before_request():
        flask.g.db = db
        flask.g.jobqueue = jobqueue
        flask.g.ingest_queue = ingest_queue


def _register_blueprints(app):
    from . import parallels, stopwords, texts, units, features, \
        multitexts, languages
    app.register_blueprint(parallels.bp)
    app.register_blueprint(stopwords.bp)
    app.register_blueprint(texts.bp)
    app.register_blueprint(units.bp)
    app.register_blueprint(features.bp)
    app.register_blueprint(multitexts.bp)
    app.register_blueprint(languages.bp)


def create_app(jobqueue, ingest_queue, test_config=None):
    """Create and configure flask application

    Parameters
    ----------
    jobqueue : tesserae.utils.coordinate.JobQueue
        interface through which searches can be scheduled
    ingest_queue : tesserae.utils.ingest.IngestQueue
        interface through which ingestion can be scheduled
    test_config : dict or None
        configuration options for database connection; if None, looks for a
        'config.py' in the same directory as the main script that calls this
        function

    """
    app = flask.Flask(__name__, instance_relative_config=True)

    _load_config(app, test_config)
    _register_before_request(app, jobqueue, ingest_queue)
    _register_blueprints(app)

    CORS(app, expose_headers=['Content-Type', 'Location'])

    @app.route('/')
    def helpful_root():
        docs_url = 'https://tesserae.caset.buffalo.edu/docs/api/'
        response = flask.Response(
            response=('The root endpoint is undefined for this API. '
                      f'See the <a href="{docs_url}">documentation</a> for '
                      'more details.'))
        response.status_code = 404
        response.status = '404 Not Found'
        return response

    return app
