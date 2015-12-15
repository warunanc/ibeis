# -*- coding: utf-8 -*-
"""
1) Ambiguity / num names
2) independence of annotations
3) continuous
4) exponential case
5) speicifc examples of our prob
6) human in loop
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import six  # NOQA
import utool as ut
import numpy as np
from six.moves import zip
from ibeis.model.hots import pgm_ext
import pgmpy
import pgmpy.inference

print, rrr, profile = ut.inject2(__name__, '[bayes]')

SPECIAL_BASIS_POOL = ['fred', 'sue', 'tom']


def test_model(num_annots, num_names, score_evidence=[], name_evidence=[],
               other_evidence={}, noquery=False, **kwargs):
    verbose = ut.VERBOSE

    model = make_name_model(num_annots, num_names, verbose=verbose, **kwargs)

    if verbose:
        model.print_priors(ignore_ttypes=['match'])

    model, evidence, soft_evidence = update_model_evidence(
        model, name_evidence, score_evidence, other_evidence)

    #if verbose:
    #    ut.colorprint('\n --- Soft Evidence ---', 'white')
    #    for ttype, cpds in model.ttype2_cpds.items():
    #        if ttype != 'match':
    #            for fs_ in ut.ichunks(cpds, 4):
    #                ut.colorprint(ut.hz_str([f._cpdstr('psql') for f in fs_]),
    #                              'green')

    if verbose:
        ut.colorprint('\n --- Inference ---', 'red')

    if (len(evidence) > 0 or len(soft_evidence) > 0) and not noquery:
        evidence = model._ensure_internal_evidence(evidence)
        query_vars = []
        query_vars += ut.list_getattr(model.ttype2_cpds['name'], 'variable')
        #query_vars += ut.list_getattr(model.ttype2_cpds['match'], 'variable')
        query_vars = ut.setdiff(query_vars, evidence.keys())
        query_results = bruteforce_query(model, query_vars, evidence)
    else:
        query_results = {}

    factor_list = query_results['factor_list']

    if verbose:
        if verbose:
            print('+--------')
        semtypes = [model.var2_cpd[f.variables[0]].ttype
                    for f in factor_list]
        for type_, factors in ut.group_items(factor_list, semtypes).items():
            print('Result Factors (%r)' % (type_,))
            factors = ut.sortedby(factors, [f.variables[0] for f in factors])
            for fs_ in ut.ichunks(factors, 4):
                ut.colorprint(ut.hz_str([f._str('phi', 'psql') for f in fs_]),
                              'yellow')
        print('MAP assignments')
        top_assignments = query_results.get('top_assignments', [])
        tmp = []
        for lbl, val in top_assignments:
            tmp.append('%s : %.4f' % (ut.repr2(lbl), val))
        print(ut.align('\n'.join(tmp), ' :'))
        print('L_____\n')

    showkw = dict(evidence=evidence,
                  soft_evidence=soft_evidence,
                  **query_results)

    show_model(model, **showkw)
    return (model, evidence)
    # pgm_ext.print_ascii_graph(model)


def make_name_model(num_annots, num_names=None, verbose=True, mode=1, num_scores=2):
    r"""
    CommandLine:
        python -m ibeis.model.hots.bayes --exec-make_name_model --show
        python -m ibeis.model.hots.bayes --exec-make_name_model
        python -m ibeis.model.hots.bayes --exec-make_name_model --num-annots=3

    Example:
        >>> # DISABLE_DOCTEST
        >>> from ibeis.model.hots.bayes import *  # NOQA
        >>> defaults = dict(num_annots=2, num_names=2, verbose=True)
        >>> kw = ut.argparse_funckw(make_name_model, defaults)
        >>> model = make_name_model(**kw)
        >>> ut.quit_if_noshow()
        >>> show_model(model, show_prior=False, show_title=False)
        >>> ut.show_if_requested()

    Ignore:
        import nx2tikz
        print(nx2tikz.dumps_tikz(model, layout='layered', use_label=True))
    """
    assert mode == 1, 'only can do mode 1'
    annots = ut.chr_range(num_annots, base=ut.get_argval('--base', default='a'))
    # The indexes of match CPDs will not change if another annotation is added
    upper_diag_idxs = ut.colwise_diag_idxs(num_annots, 2)
    if num_names is None:
        num_names = num_annots

    # +--- Define CPD Templates ---

    # +-- Name Factor ---
    name_cpd_t = pgm_ext.TemplateCPD(
        'name', ('n', num_names), varpref='N',
        special_basis_pool=SPECIAL_BASIS_POOL)
    name_cpds = [name_cpd_t.new_cpd(parents=aid) for aid in annots]
    #name_cpds = [name_cpd_t.new_cpd(parents=aid, constrain_state=count)
    #             for count, aid in enumerate(annots, start=1)]

    # +-- Match Factor ---
    def match_pmf(match_type, n1, n2):
        return {
            True: {'same': 1.0, 'diff': 0.0},
            False: {'same': 0.0, 'diff': 1.0},
        }[n1 == n2][match_type]
    states = ['diff', 'same']
    match_cpd_t = pgm_ext.TemplateCPD(
        'match', states, varpref='M',
        evidence_ttypes=[name_cpd_t, name_cpd_t], pmf_func=match_pmf)
    namepair_cpds = ut.list_unflat_take(name_cpds, upper_diag_idxs)
    match_cpds = [match_cpd_t.new_cpd(parents=cpds)
                  for cpds in namepair_cpds]

    # +-- Score Factor ---
    def score_pmf(score_type, match_type):
        if num_scores == 2:
            score_lookup = {
                'same': {'low': .1, 'high': .9, 'veryhigh': .9},
                'diff': {'low': .9, 'high': .09, 'veryhigh': .01}
            }
            val = score_lookup[match_type][score_type]
        else:
            #tmp = np.logspace(0, 1, num_scores, base=10)
            #tmp = 2 ** np.arange(num_scores)
            tmp = np.arange(num_scores + 1)[1:]
            #np.logspace(0, 1, num_scores, base=10)
            tmp = np.cumsum(tmp)
            tmp = (tmp / tmp.sum())

            if match_type == 'same':
                return tmp[score_type]
            else:
                return tmp[-(score_type + 1)]
        return val
    if num_scores == 2:
        states =  ['low', 'high']
    else:
        states = list(range(num_scores))
    score_cpd_t = pgm_ext.TemplateCPD(
        'score', states,
        varpref='S',
        evidence_ttypes=[match_cpd_t], pmf_func=score_pmf)
    score_cpds = [score_cpd_t.new_cpd(parents=cpds)
                  for cpds in zip(match_cpds)]

    # L___ End CPD Definitions ___

    cpd_list = name_cpds + score_cpds + match_cpds
    print('score_cpds = %r' % (ut.list_getattr(score_cpds, 'variable'),))

    # Make Model
    model = pgm_ext.define_model(cpd_list)
    model.num_names = num_names

    if verbose:
        model.print_templates()
    return model


def update_model_evidence(model, name_evidence, score_evidence, other_evidence):
    r"""

    CommandLine:
        python -m ibeis.model.hots.bayes --exec-update_model_evidence

    Example:
        >>> # DISABLE_DOCTEST
        >>> from ibeis.model.hots.bayes import *  # NOQA
        >>> verbose = True
        >>> other_evidence = {}
        >>> name_evidence = [0, 0, 1, 1, None]
        >>> score_evidence = ['high', 'low', 'low', 'low', 'low', 'high']
        >>> model = make_name_model(num_annots=5, num_names=3, verbose=True, mode=1)
        >>> update_model_evidence(model, name_evidence, score_evidence, other_evidence)
    """
    name_cpds = model.ttype2_cpds['name']
    score_cpds = model.ttype2_cpds['score']

    evidence = {}
    evidence.update(other_evidence)
    soft_evidence = {}

    def apply_hard_soft_evidence(cpd_list, evidence_list):
        for cpd, ev in zip(cpd_list, evidence_list):
            if isinstance(ev, int):
                # hard internal evidence
                evidence[cpd.variable] = ev
            if isinstance(ev, six.string_types):
                # hard external evidence
                evidence[cpd.variable] = cpd._internal_varindex(
                    cpd.variable, ev)
            if isinstance(ev, dict):
                # soft external evidence
                # HACK THAT MODIFIES CPD IN PLACE
                def rectify_evidence_val(_v, card=cpd.variable_card):
                    # rectify hacky string structures
                    tmp = (1 / (2 * card ** 2))
                    return (1 + tmp) / (card + tmp) if _v == '+eps' else _v
                ev_ = ut.map_dict_vals(rectify_evidence_val, ev)
                fill = (1 - sum(ev_.values())) / (cpd.variable_card - len(ev_))
                assert fill >= 0
                row_labels = list(ut.iprod(*cpd.statenames))

                for i, lbl in enumerate(row_labels):
                    if lbl in ev_:
                        # external case1
                        cpd.values[i] = ev_[lbl]
                    elif len(lbl) == 1 and lbl[0] in ev_:
                        # external case2
                        cpd.values[i] = ev_[lbl[0]]
                    elif i in ev_:
                        # internal case
                        cpd.values[i] = ev_[i]
                    else:
                        cpd.values[i] = fill
                soft_evidence[cpd.variable] = True

    apply_hard_soft_evidence(name_cpds, name_evidence)
    apply_hard_soft_evidence(score_cpds, score_evidence)
    return model, evidence, soft_evidence


def bruteforce_query(model, query_vars=None, evidence=None):
    """
    CommandLine:
        python -m ibeis.model.hots.bayes --exec-bruteforce_query --show

    Example:
        >>> # DISABLE_DOCTEST
        >>> from ibeis.model.hots.bayes import *  # NOQA
        >>> verbose = True
        >>> other_evidence = {}
        >>> name_evidence = [1, None, 0, None]
        >>> score_evidence = ['high', 'low', 'low']
        >>> model = make_name_model(num_annots=4, num_names=4, verbose=True, mode=1)
        >>> model, evidence, soft_evidence = update_model_evidence(
        >>>     model, name_evidence, score_evidence, other_evidence)
        >>> evidence = model._ensure_internal_evidence(evidence)
        >>> query_vars = ut.list_getattr(model.ttype2_cpds['name'], 'variable')
        >>> query_results = bruteforce_query(model, query_vars, evidence)
        >>> result = ('query_results = %s' % (str(query_results),))
        >>> ut.quit_if_noshow()
        >>> show_model(model, evidence=evidence, **query_results)
        >>> ut.show_if_requested()
    """
    import vtool as vt
    evidence = model._ensure_internal_evidence(evidence)

    if query_vars is None:
        query_vars = model.nodes()
    orig_query_vars = query_vars  # NOQA

    query_vars = ut.setdiff(query_vars, list(evidence.keys()))

    if True:
        operation = 'maximize'
        variables = query_vars
        # Dont brute force anymore
        infr = pgmpy.inference.BeliefPropagation(model)
        reduced_joint1 = infr.compute_conditional_joint(variables, operation, evidence)
        reduced_joint1.normalize()
        reduced_joint = reduced_joint1

        #infr = pgmpy.inference.VariableElimination(model)
        #self = infr
        #elimination_order = None  # NOQA
        #reduced_joint2 = self.compute_conditional_joint(variables, operation, evidence)
        #reduced_joint2.normalize()
    else:
        reduced_joint = model.joint_distribution().evidence_based_reduction(query_vars, evidence, inplace=False)

    evidence_vars = list(evidence.keys())
    evidence_state_idxs = ut.dict_take(evidence, evidence_vars)
    evidence_ttypes = [model.var2_cpd[var].ttype for var in evidence_vars]

    reduced_variables = reduced_joint.variables
    reduced_row_idxs = np.array(reduced_joint._row_labels(asindex=True))
    reduced_values = reduced_joint.values.ravel()
    reduced_ttypes = [model.var2_cpd[var].ttype for var in reduced_variables]

    # ttype2_ev_vars = ut.group_items(evidence_vars, evidence_ttypes)
    # ttype2_ev_idxs = ut.group_items(evidence_state_idxs, evidence_ttypes)
    ttype2_ev_indices = ut.group_items(range(len(evidence_vars)), evidence_ttypes)
    ttype2_re_indices = ut.group_items(range(len(reduced_variables)), reduced_ttypes)

    # Allow specific types of labels to change
    # everything is the same, only the names have changed.
    # TODO: allow for multiple different label_ttypes
    # for label_ttype in label_ttypes
    label_ttypes = ['name']
    for label_ttype in label_ttypes:
        ev_colxs = ttype2_ev_indices[label_ttype]
        re_colxs = ttype2_re_indices[label_ttype]

        ev_state_idxs = ut.take(evidence_state_idxs, ev_colxs)
        ev_state_idxs_tile = np.tile(ev_state_idxs, (len(reduced_values), 1)).astype(np.int)
        num_ev_ = len(ev_colxs)

        aug_colxs = list(range(num_ev_)) + (np.array(re_colxs) + num_ev_).tolist()
        aug_state_idxs = np.hstack([ev_state_idxs_tile, reduced_row_idxs])

        # Relabel rows based on the knowledge that
        # everything is the same, only the names have changed.
        def make_temp_state(state):
            mapping = {}
            for state_idx in state:
                if state_idx not in mapping:
                    mapping[state_idx] = -(len(mapping) + 1)
            temp_state = [mapping[state_idx] for state_idx in state]
            return temp_state

        num_cols = len(aug_state_idxs.T)
        mask = vt.index_to_boolmask(aug_colxs, num_cols)
        other_colxs, = np.where(~mask)
        relbl_states = aug_state_idxs.compress(mask, axis=1)
        other_states = aug_state_idxs.compress(~mask, axis=1)
        tmp_relbl_states = np.array(list(map(make_temp_state, relbl_states)))

        max_tmp_state = -1
        min_tmp_state = tmp_relbl_states.min()

        # rebuild original state structure with temp state idxs
        tmp_state_cols = [None] * num_cols
        for count, colx in enumerate(aug_colxs):
            tmp_state_cols[colx] = tmp_relbl_states[:, count:count + 1]
        for count, colx in enumerate(other_colxs):
            tmp_state_cols[colx] = other_states[:, count:count + 1]
        tmp_state_idxs = np.hstack(tmp_state_cols)

        data_ids = np.array(vt.compute_unique_data_ids_(map(tuple, tmp_state_idxs)))
        unique_ids, groupxs = vt.group_indices(data_ids)
        print('Collapsed %r states into %r states' % (len(data_ids), len(unique_ids),))
        # Sum the values in the cpd to marginalize the duplicate probs
        new_values = np.array([
            g.sum() for g in vt.apply_grouping(reduced_values, groupxs)
        ])
        # Take only the unique rows under this induced labeling
        unique_tmp_groupxs = np.array(ut.get_list_column(groupxs, 0))
        new_state_idxs = tmp_state_idxs.take(unique_tmp_groupxs, axis=0)

        tmp_idx_set = set((-np.arange(-max_tmp_state, (-min_tmp_state) + 1)).tolist())
        true_idx_set = set(range(len(model.ttype2_template[label_ttype].basis)))

        # Relabel the rows one more time to agree with initial constraints
        for colx, true_idx in enumerate(ev_state_idxs):
            tmp_idx = np.unique(new_state_idxs.T[colx])
            assert len(tmp_idx) == 1
            tmp_idx_set -= {tmp_idx[0]}
            true_idx_set -= {true_idx}
            new_state_idxs[new_state_idxs == tmp_idx] = true_idx
        # Relabel the remaining idxs
        remain_tmp_idxs = sorted(list(tmp_idx_set))[::-1]
        remain_true_idxs = sorted(list(true_idx_set))
        for tmp_idx, true_idx in zip(remain_tmp_idxs, remain_true_idxs):
            new_state_idxs[new_state_idxs == tmp_idx] = true_idx

        # Remove evidence based labels
        new_state_idxs_ = new_state_idxs.T[num_ev_:].T

        # hack into a new joint factor (that is the same size as the reduced_joint)
        new_reduced_joint = reduced_joint.copy()
        new_reduced_joint.values[:] = 0
        flat_idxs = np.ravel_multi_index(new_state_idxs_.T, new_reduced_joint.values.shape)

        old_values = new_reduced_joint.values.ravel()
        old_values[flat_idxs] = new_values
        new_reduced_joint.values = old_values.reshape(reduced_joint.cardinality)
        # print(new_reduced_joint._str(maxrows=4, sort=-1))

    max_marginals = {}
    for i, var in enumerate(query_vars):
        one_out = query_vars[:i] + query_vars[i + 1:]
        max_marginals[var] = new_reduced_joint.marginalize(one_out, inplace=False)
        # max_marginals[var] = joint2.maximize(one_out, inplace=False)

    factor_list = max_marginals.values()

    # Now find the most likely state
    sortx = new_values.argsort()[::-1]
    sort_new_state_idxs_ = new_state_idxs_.take(sortx, axis=0)
    sort_new_values = new_values.take(sortx)
    reduced_joint.variables
    sort_new_states = list(zip(*[ut.dict_take(reduced_joint.statename_dict[var], idx)
                                 for var, idx in
                                 zip(reduced_joint.variables, sort_new_state_idxs_.T)]))

    # Better map assignment based on knowledge of labels
    map_assign = dict(zip(reduced_joint.variables, sort_new_states[0]))

    sort_reduced_rowstr_lbls = [
        ut.repr2(dict(zip(reduced_joint.variables, lbls)), explicit=True, nobraces=True,
                 strvals=True)
        for lbls in sort_new_states
    ]

    top_assignments = list(zip(sort_reduced_rowstr_lbls[:4], sort_new_values))
    if len(sort_new_values) > 3:
        top_assignments += [('other', 1 - sum(sort_new_values[:4]))]
    query_results = {
        'factor_list': factor_list,
        'top_assignments': top_assignments,
        'map_assign': map_assign,
        'marginalized_joints': None,
    }
    return query_results


def draw_tree_model(model, **kwargs):
    import plottool as pt
    import networkx as netx
    if not ut.get_argval('--hackjunc'):
        fnum = pt.ensure_fnum(None)
        fig = pt.figure(fnum=fnum, doclf=True)  # NOQA
        ax = pt.gca()
        #name_nodes = sorted(ut.list_getattr(model.ttype2_cpds['name'], 'variable'))
        netx_graph = model.to_markov_model()
        #pos = netx.pygraphviz_layout(netx_graph)
        #pos = netx.graphviz_layout(netx_graph)
        #pos = get_hacked_pos(netx_graph, name_nodes, prog='neato')
        pos = netx.pydot_layout(netx_graph)
        node_color = [pt.WHITE] * len(pos)
        drawkw = dict(pos=pos, ax=ax, with_labels=True, node_color=node_color,
                      node_size=1100)
        netx.draw(netx_graph, **drawkw)
        if kwargs.get('show_title', True):
            pt.set_figtitle('Markov Model')

    if not ut.get_argval('--hackmarkov'):
        fnum = pt.ensure_fnum(None)
        fig = pt.figure(fnum=fnum, doclf=True)  # NOQA
        ax = pt.gca()
        netx_graph = model.to_junction_tree()
        # prettify nodes
        def fixtupkeys(dict_):
            return {
                ', '.join(k) if isinstance(k, tuple) else k: fixtupkeys(v)
                for k, v in dict_.items()
            }
        n = fixtupkeys(netx_graph.node)
        e = fixtupkeys(netx_graph.edge)
        a = fixtupkeys(netx_graph.adj)
        netx_graph.node = n
        netx_graph.edge = e
        netx_graph.adj = a
        #netx_graph = model.to_markov_model()
        #pos = netx.pygraphviz_layout(netx_graph)
        #pos = netx.graphviz_layout(netx_graph)
        pos = netx.pydot_layout(netx_graph)
        node_color = [pt.WHITE] * len(pos)
        drawkw = dict(pos=pos, ax=ax, with_labels=True, node_color=node_color,
                      node_size=2000)
        netx.draw(netx_graph, **drawkw)
        if kwargs.get('show_title', True):
            pt.set_figtitle('Junction/Clique Tree / Cluster Graph')


def get_hacked_pos(netx_graph, name_nodes=None, prog='dot'):
    import pygraphviz
    import networkx as netx
    # Add "invisible" edges to induce an ordering
    # Hack for layout (ordering of top level nodes)
    netx_graph2 = netx_graph.copy()
    if getattr(netx_graph, 'ttype2_cpds', None) is not None:
        grouped_nodes = []
        for ttype in netx_graph.ttype2_cpds.keys():
            ttype_cpds = netx_graph.ttype2_cpds[ttype]
            # use defined ordering
            ttype_nodes = ut.list_getattr(ttype_cpds, 'variable')
            # ttype_nodes = sorted(ttype_nodes)
            invis_edges = list(ut.itertwo(ttype_nodes))
            netx_graph2.add_edges_from(invis_edges)
            grouped_nodes.append(ttype_nodes)

        A = netx.to_agraph(netx_graph2)
        for nodes in grouped_nodes:
            A.add_subgraph(nodes, rank='same')
    else:
        A = netx.to_agraph(netx_graph2)

    #if name_nodes is not None:
    #    #netx.set_node_attributes(netx_graph, 'label', {n: {'label': n} for n in all_nodes})
    #    invis_edges = list(ut.itertwo(name_nodes))
    #    netx_graph2.add_edges_from(invis_edges)
    #    A.add_subgraph(name_nodes, rank='same')
    #else:
    #    A = netx.to_agraph(netx_graph2)
    args = ''
    G = netx_graph
    A.layout(prog=prog, args=args)
    #A.draw('example.png', prog='dot')
    node_pos = {}
    for n in G:
        node_ = pygraphviz.Node(A, n)
        try:
            xx, yy = node_.attr["pos"].split(',')
            node_pos[n] = (float(xx), float(yy))
        except:
            print("no position for node", n)
            node_pos[n] = (0.0, 0.0)
    return node_pos


def show_model(model, evidence={}, soft_evidence={}, **kwargs):
    """
    References:
        http://stackoverflow.com/questions/22207802/pygraphviz-networkx-set-node-level-or-layer

    Ignore:
        pkg-config --libs-only-L libcgraph
        sudo apt-get  install libgraphviz-dev -y
        sudo apt-get  install libgraphviz4 -y

        # sudo apt-get install pkg-config
        sudo apt-get install libgraphviz-dev
        # pip install git+git://github.com/pygraphviz/pygraphviz.git
        pip install pygraphviz
        python -c "import pygraphviz; print(pygraphviz.__file__)"

        sudo pip3 install pygraphviz --install-option="--include-path=/usr/include/graphviz" --install-option="--library-path=/usr/lib/graphviz/"
        python3 -c "import pygraphviz; print(pygraphviz.__file__)"

    CommandLine:
        python -m ibeis.model.hots.bayes --exec-show_model --show

    Example:
        >>> # DISABLE_DOCTEST
        >>> from ibeis.model.hots.bayes import *  # NOQA
        >>> model = '?'
        >>> evidence = {}
        >>> soft_evidence = {}
        >>> result = show_model(model, evidence, soft_evidence)
        >>> print(result)
        >>> ut.quit_if_noshow()
        >>> import plottool as pt
        >>> ut.show_if_requested()
    """
    if ut.get_argval('--hackmarkov') or ut.get_argval('--hackjunc'):
        draw_tree_model(model, **kwargs)
        return

    import plottool as pt
    import networkx as netx
    fnum = pt.ensure_fnum(None)
    netx_graph = (model)
    #netx_graph.graph.setdefault('graph', {})['size'] = '"10,5"'
    #netx_graph.graph.setdefault('graph', {})['rankdir'] = 'LR'

    pos_dict = get_hacked_pos(netx_graph)
    #pos_dict = netx.pygraphviz_layout(netx_graph)
    #pos = netx.pydot_layout(netx_graph, prog='dot')
    #pos_dict = netx.graphviz_layout(netx_graph)

    textprops = {
        'family': 'monospace',
        'horizontalalignment': 'left',
        #'horizontalalignment': 'center',
        #'size': 12,
        'size': 8,
    }

    netx_nodes = model.nodes(data=True)
    node_key_list = ut.get_list_column(netx_nodes, 0)
    pos_list = ut.dict_take(pos_dict, node_key_list)

    var2_post = {f.variables[0]: f for f in kwargs.get('factor_list', [])}

    prior_text = None
    post_text = None
    evidence_tas = []
    post_tas = []
    prior_tas = []
    node_color = []

    show_prior_with_ttype = ['name']

    dpy = 5
    dbx, dby = (20, 20)
    takw1 = {'bbox_align': (.5, 0), 'pos_offset': [0, dpy], 'bbox_offset': [dbx, dby]}
    takw2 = {'bbox_align': (.5, 1), 'pos_offset': [0, -dpy], 'bbox_offset': [-dbx, -dby]}

    name_colors = pt.distinct_colors(model.num_names + 1)

    for node, pos in zip(netx_nodes, pos_list):
        variable = node[0]
        cpd = model.var2_cpd[variable]
        prior_marg = (cpd if cpd.evidence is None else
                      cpd.marginalize(cpd.evidence, inplace=False))

        show_evidence = variable in evidence
        show_prior = cpd.ttype in show_prior_with_ttype
        show_post = variable in var2_post
        show_prior |= cpd.ttype in show_prior_with_ttype

        post_marg = None
        show_prior = False

        if show_post:
            post_marg = var2_post[variable]

        #cmap_ = 'hot'
        #mx = 0.65
        #mn = 0.15
        cmap_ = 'plasma'
        _cmap = pt.plt.get_cmap(cmap_)
        mx = 1.0
        mn = 0.15
        def cmap(x):
            return _cmap((x * mx) + mn)
        if variable in evidence:
            if cpd.ttype == 'score':
                cmap_index = evidence[variable] / (cpd.variable_card - 1)
                color = cmap(cmap_index)
                color = pt.lighten_rgb(color, .4)
                color = np.array(color)
                node_color.append(color)
            elif cpd.ttype == 'name':
                color = name_colors[evidence[variable]]
                color = np.array(color)
                node_color.append(color)
            else:
                color = pt.FALSE_RED
                node_color.append(color)
        elif variable in soft_evidence:
            color = pt.LIGHT_PINK
            node_color.append(color)
        else:
            if cpd.ttype == 'name' and post_marg is not None:
                order = post_marg.values.argsort()[::-1]
                dist_next = post_marg.values[order[0]] - post_marg.values[order[1]]
                dist_total = (post_marg.values[order[0]])
                confidence = (dist_total * dist_next) ** (2.5 / 4)
                #print('confidence = %r' % (confidence,))
                color = name_colors[order[0]]
                color = pt.color_funcs.desaturate_rgb(color, 1 - confidence)
                color = np.array(color)
                node_color.append(color)
                #import utool
                #utool.embed()
            elif cpd.ttype == 'match' and post_marg is not None:
                color = cmap(post_marg.values[1])
                color = pt.lighten_rgb(color, .4)
                color = np.array(color)
                node_color.append(color)
            else:
                color = pt.WHITE
                node_color.append(color)

        if show_prior:
            prior_text = pgm_ext.make_factor_text(prior_marg, 'prior')
            prior_tas.append(dict(text=prior_text, pos=pos, color=color, **takw2))
        if show_evidence:
            _takw1 = takw1
            if cpd.ttype == 'score':
                _takw1 = takw2
            evidence_text = cpd.variable_statenames[evidence[variable]]
            if isinstance(evidence_text, int):
                evidence_text = '%d/%d' % (evidence_text + 1, cpd.variable_card)
            #import utool
            #utool.embed()
            evidence_tas.append(dict(text=evidence_text, pos=pos, color=color, **_takw1))
        if show_post:
            _takw1 = takw1
            if cpd.ttype == 'match':
                _takw1 = takw2
            post_text = pgm_ext.make_factor_text(post_marg, 'post')
            post_tas.append(dict(text=post_text, pos=pos, color=None, **_takw1))

    def augkey(key):
        return key + '_list'

    def trnps_(dict_list):
        """ tranpose dict list """
        list_dict = ut.ddict(list)
        for dict_ in dict_list:
            for key, val in dict_.items():
                list_dict[augkey(key)].append(val)
        return list_dict

    takw1_ = trnps_(post_tas + evidence_tas)
    takw2_ = trnps_(prior_tas)
    #takw1_ = ut.dict_union(trnps_(post_tas + evidence_tas), ut.map_dict_keys(augkey, takw1))
    #takw2_ = ut.dict_union(trnps_(prior_tas), ut.map_dict_keys(augkey, takw2))

    # Draw graph
    fig = pt.figure(fnum=fnum, pnum=(3, 1, (slice(0, 2), 0)), doclf=True)  # NOQA
    ax = pt.gca()
    #print('node_color = %s' % (ut.repr3(node_color),))
    drawkw = dict(pos=pos_dict, ax=ax, with_labels=True, node_size=1500,
                  node_color=node_color)
    netx.draw(netx_graph, **drawkw)
    hack1 = pt.draw_text_annotations(textprops=textprops, **takw1_)
    if prior_tas:
        hack2 = pt.draw_text_annotations(textprops=textprops, **takw2_)

    xmin, ymin = np.array(pos_list).min(axis=0)
    xmax, ymax = np.array(pos_list).max(axis=0)
    num_annots = len(model.ttype2_cpds['name'])
    if num_annots > 4:
        ax.set_xlim((xmin - 40, xmax + 40))
        ax.set_ylim((ymin - 50, ymax + 50))
        fig.set_size_inches(30, 7)
    else:
        ax.set_xlim((xmin - 42, xmax + 42))
        ax.set_ylim((ymin - 50, ymax + 50))
        fig.set_size_inches(23, 7)
    fig = pt.gcf()

    title = 'num_names=%r, num_annots=%r' % (model.num_names, num_annots,)
    map_assign = kwargs.get('map_assign', None)

    top_assignments = kwargs.get('top_assignments', None)
    if top_assignments is not None:
        map_assign, map_prob = top_assignments[0]
        if map_assign is not None:
            title += '\nMAP: ' + map_assign + ' @' + '%.2f%%' % (100 * map_prob,)
    if kwargs.get('show_title', True):
        pt.set_figtitle(title, size=14)

    hack1()
    if prior_tas:
        hack2()

    # Hack in colorbars
    pt.colorbar(np.linspace(0, 1, len(name_colors) - 1), name_colors[:-1], lbl='name',
                ticklabels=model.ttype2_template['name'].basis, ticklocation='left')

    scalars = np.linspace(0, 1, 100)
    colors = pt.scores_to_color(scalars, cmap_=cmap_, reverse_cmap=False,
                                cmap_range=(mn, mx))
    colors = [pt.lighten_rgb(c, .4) for c in colors]
    basis = model.ttype2_template['score'].basis

    if ut.list_type(basis) is int:
        pt.colorbar(scalars, colors, lbl='score', ticklabels=np.array(basis) + 1)
    else:
        pt.colorbar(scalars, colors, lbl='score', ticklabels=basis)

    # Draw probability hist
    if top_assignments is not None:
        bin_labels = ut.get_list_column(top_assignments, 0)
        bin_vals =  ut.get_list_column(top_assignments, 1)

        # bin_labels = ['\n'.join(ut.textwrap.wrap(_lbl, width=30)) for _lbl in bin_labels]

        pt.draw_histogram(bin_labels, bin_vals, fnum=fnum, pnum=(3, 8, (2, slice(4, None))),
                          transpose=True,
                          use_darkbackground=False,
                          #xtick_rotation=-10,
                          ylabel='Prob', xlabel='assignment')
        pt.set_title('Assignment probabilities')
    #fpath = ('name_model_' + suff + '.png')
    #pt.plt.savefig(fpath)
    #return fpath


if __name__ == '__main__':
    r"""
    CommandLine:
        python -m ibeis.model.hots.bayes
        python -m ibeis.model.hots.bayes --allexamples
    """
    import multiprocessing
    multiprocessing.freeze_support()  # for win32
    import utool as ut  # NOQA
    ut.doctest_funcs()
