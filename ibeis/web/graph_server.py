# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals
import utool as ut
import random
import time
# from ibeis.web import futures_utils as futures_actors
import futures_actors
print, rrr, profile = ut.inject2(__name__)


def ut_to_json_encode(dict_):
    # Encode correctly for UUIDs and other information
    for key in dict_:
        dict_[key] = ut.to_json(dict_[key])
    return dict_


def testdata_start_payload(aids='all'):
    import ibeis
    payload = {
        'action'       : 'start',
        'dbdir'        : ibeis.sysres.db_to_dbdir('PZ_MTEST'),
        'aids'         : aids,
    }
    return payload


def testdata_feedback_payload(edge, decision):
    payload = {
        'action': 'add_feedback',
        'edge': edge,
        'evidence_decision': decision,
        'meta_decision': 'null',
        'tags': [],
        'user_id': 'user:doctest',
        'confidence': 'pretty_sure',
        'timestamp_s1': 1,
        'timestamp_c1': 2,
        'timestamp_c2': 3,
        'timestamp': 4,
    }
    return payload


def test_foo(future):
    print('FOO %r' % (future, ))


class GraphActor(futures_actors.ProcessActor):
    """

    CommandLine:
        python -m ibeis.web.graph_server GraphActor

    Doctest:
        >>> from ibeis.web.graph_server import *
        >>> actor = GraphActor()
        >>> payload = testdata_start_payload()
        >>> locals().update(payload)
        >>> # Start the process
        >>> user_request = actor.handle(payload)
        >>> # Respond with a user decision
        >>> edge, priority, edge_data = user_request[0]
        >>> user_resp_payload = {
        >>>     'action': 'add_feedback',
        >>>     'edge': edge,
        >>>     'evidence_decision': 'match',
        >>>     'meta_decision': 'null',
        >>>     'tags': [],
        >>>     'user_id': 'user:doctest',
        >>>     'confidence': 'pretty_sure',
        >>>     'timestamp_s1': 1,
        >>>     'timestamp_c1': 2,
        >>>     'timestamp_c2': 3,
        >>>     'timestamp': 4,
        >>> }
        >>> content = actor.handle(user_resp_payload)
        >>> actor.infr.dump_logs()

    """
    def __init__(actor):
        actor.infr = None

    def handle(actor, message):
        if not isinstance(message, dict):
            raise ValueError('Commands must be passed in a message dict')
        message = message.copy()
        action = message.pop('action', None)
        if action is None:
            raise ValueError('Payload must have an action item')
        if action == 'wait':
            num = message.get('num', 0)
            time.sleep(num)
            return message
        elif action == 'debug':
            return actor
        elif action == 'error':
            raise Exception('FOOBAR')
        elif action == 'logs':
            return actor.infr.logs
        else:
            func = getattr(actor, action, None)
            if func is None:
                raise ValueError('Unknown action=%r' % (action,))
            else:
                return func(**message)

    def start(actor, dbdir, aids='all', config={},
              **kwargs):
        import ibeis
        assert dbdir is not None, 'must specify dbdir'
        assert actor.infr is None, ('AnnotInference already running')
        ibs = ibeis.opendb(dbdir=dbdir, use_cache=False, web=False,
                           force_serial=True)
        # Create the AnnotInference
        actor.infr = ibeis.AnnotInference(ibs=ibs, aids=aids, autoinit=True)
        # Configure query_annot_infr
        actor.infr.params['manual.n_peek'] = 50
        # actor.infr.params['autoreview.enabled'] = False
        actor.infr.params['redun.pos'] = 2
        actor.infr.params['redun.neg'] = 2
        # Initialize
        # TODO: Initialize state from staging reviews after annotmatch
        # timestamps (in case of crash)
        actor.infr.reset_feedback('annotmatch', apply=True)
        actor.infr.ensure_mst()

        # Load random forests (TODO: should this be config specifiable?)
        actor.infr.load_published()

        actor.infr.apply_nondynamic_update()
        return 'started'

    def refresh(actor):
        # Start actor.infr Main Loop
        actor.infr.refresh_candidate_edges()
        return actor.continue_review()

    def continue_review(actor):
        # This will signal on_request_review with the same data
        user_request = actor.infr.continue_review()
        return user_request

    def add_feedback(actor, **feedback):
        return actor.infr.on_accept(feedback, need_next=False)


@ut.reloadable_class
class GraphClient(object):
    """
    CommandLine:
        python -m ibeis.web.graph_server GraphClient

    Example:
        >>> from ibeis.web.graph_server import *
        >>> import ibeis
        >>> client = GraphClient(autoinit=True)
        >>> # Start the GraphActor in another proc
        >>> payload = testdata_start_payload()
        >>> client.post(payload).result()
        >>> f1 = client.post({'action': 'refresh'})
        >>> f1.add_done_callback(test_foo)
        >>> user_request = f1.result()
        >>> # Wait for a response and  the GraphActor in another proc
        >>> edge, priority, edge_data = user_request[0]
        >>> user_resp_payload = testdata_feedback_payload(edge, 'match')
        >>> f2 = client.post(user_resp_payload)
        >>> f2.result()
        >>> # Debug by getting the actor over a mp.Pipe
        >>> f3 = client.post({'action': 'debug'})
        >>> actor = f3.result()
        >>> actor.infr.dump_logs()
        >>> #print(client.post({'action': 'logs'}).result())

    Ignore:
        >>> from ibeis.web.graph_server import *
        >>> import ibeis
        >>> client = GraphClient(autoinit=True)
        >>> # Start the GraphActor in another proc
        >>> client.post(testdata_start_payload(list(range(1, 10)))).result()
        >>> #
        >>> f1 = client.post({'action': 'refresh'})
        >>> user_request = f1.result()
        >>> # The infr algorithm needs a review
        >>> edge, priority, edge_data = user_request[0]
        >>> #
        >>> client.post(testdata_feedback_payload(edge, 'match'))
        >>> client.post({'action': 'continue_review'})
        >>> client.post(testdata_feedback_payload(edge, 'match'))
        >>> client.post(testdata_feedback_payload(edge, 'match'))
        >>> client.post({'action': 'continue_review'})
        >>> client.post(testdata_feedback_payload(edge, 'match'))
        >>> client.post({'action': 'wait', 'num': float(30)})
        >>> client.post({'action': 'continue_review'})
        >>> client.post(testdata_feedback_payload(edge, 'match'))
        >>> client.post(testdata_feedback_payload(edge, 'match'))
        >>> client.post({'action': 'continue_review'})
        >>> client.post(testdata_feedback_payload(edge, 'match'))
        >>> client.post({'action': 'continue_review'})
        >>> client.post(testdata_feedback_payload(edge, 'match'))
        >>> client.post({'action': 'continue_review'})
        >>> client.post(testdata_feedback_payload(edge, 'match'))
        >>> client.post(testdata_feedback_payload(edge, 'match'))
        >>> client.post({'action': 'continue_review'})
        >>> client.post(testdata_feedback_payload(edge, 'match'))
        >>> client.post({'action': 'continue_review'})
        >>> client.post(testdata_feedback_payload(edge, 'match'))
        >>> client.post({'action': 'continue_review'})
        >>> client.post(testdata_feedback_payload(edge, 'match'))
        >>> client.post(testdata_feedback_payload(edge, 'match'))
        >>> client.post({'action': 'continue_review'})
        >>> client.post(testdata_feedback_payload(edge, 'match'))
        >>> client.post({'action': 'continue_review'})
        >>> client.post(testdata_feedback_payload(edge, 'match'))
        >>> client.post({'action': 'continue_review'})

    """
    def __init__(client, graph_uuid=None, callbacks={}, autoinit=False):
        client.graph_uuid = graph_uuid
        client.callbacks = callbacks
        client.review_dict = {}
        client.review_vip = None
        client.futures = []
        if autoinit:
            client.initialize()

    def initialize(client):
        client.executor = GraphActor.executor()

    def post(client, payload):
        if not isinstance(payload, dict) or 'action' not in payload:
            raise ValueError('payload must be a dict with an action')
        future = client.executor.post(payload)
        client.futures.append((payload['action'], future))
        return future

    def cleanup(client):
        # remove done items from our list
        new_futures = []
        for action, future in client.futures:
            if not future.done():
                if future.running():
                    new_futures.append((action, future))
                elif action == 'continue_review':
                    future.cancel()
                else:
                    new_futures.append((action, future))
        client.futures = new_futures

    def update(client, data_list):
        client.review_dict = {}
        client.review_vip = None
        for (edge, priority, edge_data_dict) in data_list:
            aid1, aid2 = edge
            if aid2 < aid1:
                aid1, aid2 = aid2, aid1
            edge = (aid1, aid2, )
            if client.review_vip is None:
                client.review_vip = edge
            client.review_dict[edge] = (priority, edge_data_dict, )

    def sample(client):
        edge_list = list(client.review_dict.keys())
        if len(edge_list) == 0:
            return None
        if client.review_vip is not None and client.review_vip in edge_list:
            edge = client.review_vip
            client.review_vip = None
        else:
            edge = random.choice(edge_list)
        priority, data_dict = client.review_dict[edge]
        return edge, priority, data_dict


if __name__ == '__main__':
    """
    CommandLine:
        python -m ibeis.web.job_engine
        python -m ibeis.web.job_engine --allexamples
        python -m ibeis.web.job_engine --allexamples --noface --nosrc
    """
    import multiprocessing
    multiprocessing.freeze_support()  # for win32
    import utool as ut  # NOQA
    ut.doctest_funcs()