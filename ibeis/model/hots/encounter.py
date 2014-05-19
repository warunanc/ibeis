from __future__ import absolute_import, division, print_function
import utool
(print, print_,  rrr, profile,
 printDBG) = utool.inject(__name__, '[encounter]', DEBUG=False)
# Python
from itertools import izip
# Science
import networkx as netx
import numpy as np
# HotSpotter
from ibeis.model.hots import match_chips3 as mc3

import utool


def build_encounter_ids(ex2_gxs, gid2_clusterid):
    USE_STRING_ID = True
    gid2_eid = [None] * len(gid2_clusterid)
    for ex, gids in enumerate(ex2_gxs):
        for gid in gids:
            nGx = len(gids)
            gid2_eid[gid] = ('ex=%r_nGxs=%d' % (ex, nGx)
                             if USE_STRING_ID else
                             ex + (nGx / 10 ** np.ceil(np.log(nGx) / np.log(10))))


def get_chip_encounters(ibs):
    gid2_ex, ex2_gxs = compute_encounters(ibs)  # NOQA
    # Build encounter to chips from encounter to images
    ex2_cxs = [None for _ in xrange(len(ex2_gxs))]
    for ex, gids in enumerate(ex2_gxs):
        ex2_cxs[ex] = utool.flatten(ibs.gid2_cxs(gids))
    # optional
    # resort encounters by number of chips
    ex2_nCxs = map(len, ex2_cxs)
    ex2_cxs = [y for (x, y) in sorted(zip(ex2_nCxs, ex2_cxs))]
    return ex2_cxs


def get_fmatch_iter(res):
    # USE res.get_fmatch_iter()
    fmfsfk_enum = enumerate(izip(res.rid2_fm, res.rid2_fs, res.rid2_fk))
    fmatch_iter = ((rid, fx_tup, score, rank)
                   for rid, (fm, fs, fk) in fmfsfk_enum
                   for (fx_tup, score, rank) in izip(fm, fs, fk))
    return fmatch_iter


def get_cxfx_enum(qreq):
    ax2_cxs = qreq._data_index.ax2_cx
    ax2_fxs = qreq._data_index.ax2_fx
    ridfx_enum = enumerate(izip(ax2_cxs, ax2_fxs))
    return ridfx_enum


def intra_query_cxs(ibs, rids):
    dcxs = qcxs = rids
    qreq = mc3.prep_query_request(qreq=ibs.qreq, qcxs=qcxs, dcxs=dcxs,
                                  query_cfg=ibs.prefs.query_cfg)
    qcx2_res = mc3.process_query_request(ibs, qreq)
    return qcx2_res


#def intra_encounter_match(ibs, rids, **kwargs):
    # Make a graph between the chips
    #qcx2_res = intra_query_cxs(rids)
    #graph = make_chip_graph(qcx2_res)
    # TODO: Make a super cool algorithm which does this correctly
    #graph.cutEdges(**kwargs)
    # Get a temporary name id
    # TODO: ensure these name indexes do not conflict with other encounters
    #rid2_nx, nid2_cxs = graph.getConnectedComponents()
    #return graph


def execute_all_intra_encounter_match(ibs, **kwargs):
    # Group images / chips into encounters
    ex2_cxs = get_chip_encounters(ibs)
    # For each encounter
    ex2_names = {}
    for ex, rids in enumerate(ex2_cxs):
        pass
        # Perform Intra-Encounter Matching
        #nid2_cxs = intra_encounter_match(ibs, rids)
        #ex2_names[ex] = nid2_cxs
    return ex2_names


def inter_encounter_match(ibs, eid2_names=None, **kwargs):
    # Perform Inter-Encounter Matching
    #if eid2_names is None:
        #eid2_names = intra_encounter_match(ibs, **kwargs)
    all_nxs = utool.flatten(eid2_names.values())
    for nid2_cxs in eid2_names:
        qnxs = nid2_cxs
        dnxs = all_nxs
        name_result = ibs.query(qnxs=qnxs, dnxs=dnxs)
    qcx2_res = name_result.chip_results()
    graph = netx.Graph()
    graph.add_nodes_from(range(len(qcx2_res)))
    graph.add_edges_from([res.rid2_fm for res in qcx2_res.itervalues()])
    graph.setWeights([(res.rid2_fs, res.rid2_fk) for res in qcx2_res.itervalues()])
    graph.cutEdges(**kwargs)
    rid2_nx, nid2_cxs = graph.getConnectedComponents()
    return rid2_nx


def print_encounter_stats(ex2_cxs):
    ex2_nCxs = map(len, ex2_cxs)
    ex_statstr = utool.common_stats(ex2_nCxs)
    print('num_encounters = %r' % len(ex2_nCxs))
    print('encounter_stats = %r' % (ex_statstr,))
