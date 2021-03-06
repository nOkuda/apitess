"""The family of /multitexts/ endpoints"""
import gzip
import os
import queue
import uuid

import flask
from flask_cors import cross_origin

import apitess.errors
import apitess.utils
import tesserae.utils.multitext

bp = flask.Blueprint('multitexts', __name__, url_prefix='/multitexts')


@bp.route('/', methods=(
    'POST',
    'OPTIONS',
))
@cross_origin(expose_headers='Location')
def submit_multitext():
    """Run multitext search"""
    error_response, received = apitess.errors.check_body(flask.request)
    if error_response:
        return error_response
    requireds = {'parallels_uuid', 'text_ids', 'unit_type'}
    miss_error = apitess.errors.check_requireds(received, requireds)
    if miss_error:
        return miss_error

    results = flask.g.db.find(tesserae.db.entities.Search.collection,
                              results_id=received['parallels_uuid'],
                              search_type=tesserae.utils.search.NORMAL_SEARCH)
    if not results:
        return apitess.errors.error(
            400,
            data=received,
            message='Unable to find completed Tesserae search: {}'.format(
                received['parallels_uuid']))

    if not received['text_ids']:
        return apitess.errors.error(
            400,
            data=received,
            message='Cannot run multitext search on empty selection of texts')
    _, failures = apitess.utils.make_object_ids(received['text_ids'])
    if failures:
        return apitess.errors.error(
            400,
            data=received,
            message='Malformed object_ids specified in "texts": {}'.format(
                failures))

    accepted_unit_types = ['line', 'phrase']
    if received['unit_type'] not in accepted_unit_types:
        return apitess.errors.error(
            400,
            data=received,
            message=(f'Specified unit_type ({received["unit_type"]}) is not '
                     f'acceptable; acceptable values: {accepted_unit_types}'))

    results_id = tesserae.utils.multitext.check_cache(
        flask.g.db, received['parallels_uuid'], received['text_ids'],
        received['unit_type'])
    if results_id:
        response = flask.Response()
        response.status_code = 303
        response.status = '303 See Other'
        # Redirect should point to paginated results
        response.headers['Location'] = os.path.join(
            flask.request.base_url, results_id, '?' + '&'.join(
                f'{a}={b}' for a, b in {
                    'sort_by': 'score',
                    'sort_order': 'descending',
                    'per_page': '100',
                    'page_number': '0'
                }.items()))
        return response

    response = flask.Response()
    response.status_code = 201
    response.status = '201 Created'
    results_id = uuid.uuid4().hex
    # we want the final '/' on the URL
    response.headers['Location'] = os.path.join(flask.request.base_url,
                                                results_id, '')

    try:
        tesserae.utils.multitext.submit_multitext(flask.g.jobqueue, flask.g.db,
                                                  results_id,
                                                  received['parallels_uuid'],
                                                  received['text_ids'],
                                                  received['unit_type'])
    except queue.Full:
        return apitess.error.error(
            500,
            data=received,
            message=('The search request could not be added to the queue. '
                     'Please try again in a few minutes'))
    return response


@bp.route('/<results_id>/status/')
@cross_origin()
def retrieve_status(results_id):
    return apitess.utils.common_retrieve_status(
        flask.g.db.find, results_id, tesserae.utils.multitext.MULTITEXT_SEARCH)


@bp.route('/<results_id>/')
@cross_origin()
def retrieve_results(results_id):
    # get search results
    results_status_found = flask.g.db.find(
        tesserae.db.entities.Search.collection,
        results_id=results_id,
        search_type=tesserae.utils.multitext.MULTITEXT_SEARCH)
    if not results_status_found:
        response = flask.Response('Could not find results_id')
        response.status_code = 404
        return response
    if results_status_found[0].status != tesserae.db.entities.Search.DONE:
        status_url = os.path.join(flask.request.base_url, results_id, 'status',
                                  '')
        response = flask.Response(
            f'Unable to retrieve results; check {status_url} endpoint.')
        response.headers['Cache-Control'] = 'no-store'
        response.status_code = 404
        return response

    url_query_params = flask.request.args
    page_options, err = apitess.utils.get_page_options_or_error(
        url_query_params)
    if err:
        return err

    params = results_status_found[0].parameters

    multiresults = [
        mr for mr in tesserae.utils.multitext.get_results(
            flask.g.db, results_status_found[0].id, page_options)
    ]
    search_id = tesserae.utils.search.get_id_by_uuid(flask.g.db,
                                                     params['parallels_uuid'])
    response = flask.Response(
        response=gzip.compress(
            flask.json.dumps({
                'data':
                params,
                'max_score':
                tesserae.utils.search.get_max_score(flask.g.db, search_id),
                'total_count':
                tesserae.utils.search.get_results_count(flask.g.db, search_id),
                'multiresults':
                multiresults
            }).encode()),
        mimetype='application/json',
    )
    response.status_code = 200
    response.status = '200 OK'
    response.headers['Content-Encoding'] = 'gzip'

    results_status_found[0].update_last_queried()
    flask.g.db.update(results_status_found[0])
    return response
