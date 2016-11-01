# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals
import numpy as np
import warnings
import utool as ut
import vtool as vt  # NOQA
import six
import networkx as nx
import plottool as pt
print, rrr, profile = ut.inject2(__name__)


def _dz(a, b):
    a = a.tolist() if isinstance(a, np.ndarray) else list(a)
    b = b.tolist() if isinstance(b, np.ndarray) else list(b)
    return ut.dzip(a, b)


@six.add_metaclass(ut.ReloadingMetaclass)
class _AnnotInfrViz(object):
    """ contains plotting related code """

    def _get_truth_colors(infr):
        truth_colors = {
            # 'match': pt.TRUE_GREEN,
            'match': pt.TRUE_BLUE,
            'nomatch': pt.FALSE_RED,
            'notcomp': pt.YELLOW,
            'unreviewed': pt.UNKNOWN_PURP
        }
        return truth_colors

    def _get_cmap(infr):
        # return pt.plt.cm.RdYlBu
        if hasattr(infr, '_cmap'):
            return infr._cmap
        else:
            cpool = np.array([[ 0.98135718,  0.19697982,  0.02117342],
                              [ 1.        ,  0.33971852,  0.        ],
                              [ 1.        ,  0.45278535,  0.        ],
                              [ 1.        ,  0.55483746,  0.        ],
                              [ 1.        ,  0.65106306,  0.        ],
                              [ 1.        ,  0.74359729,  0.        ],
                              [ 1.        ,  0.83348477,  0.        ],
                              [ 0.98052302,  0.92128928,  0.        ],
                              [ 0.95300175,  1.        ,  0.        ],
                              [ 0.59886986,  0.99652954,  0.23932718],
                              [ 0.2       ,  0.95791134,  0.44764457],
                              [ 0.2       ,  0.89937643,  0.63308702],
                              [ 0.2       ,  0.82686023,  0.7895433 ],
                              [ 0.2       ,  0.74361034,  0.89742738],
                              [ 0.2       ,  0.65085832,  0.93960823],
                              [ 0.2       ,  0.54946918,  0.90949295],
                              [ 0.25697101,  0.44185497,  0.8138502 ]])
            cmap = pt.mpl.colors.ListedColormap(cpool, 'indexed')
            # cmap = pt.interpolated_colormap([
            #     (pt.FALSE_RED, 0.0),
            #     (pt.YELLOW, 0.5),
            #     (pt.TRUE_BLUE, 1.0),
            # ], resolution=128)
            infr._cmap = cmap
            return infr._cmap

    def initialize_visual_node_attrs(infr, graph=None):
        if infr.verbose >= 3:
            print('[infr] initialize_visual_node_attrs')
        import networkx as nx
        if graph is None:
            graph = infr.graph
        aid_to_node = infr.aid_to_node
        aid_list = list(aid_to_node.keys())
        annot_nodes = ut.take(aid_to_node, aid_list)
        chip_width = 256
        imgpath_list = infr.ibs.depc_annot.get('chips', aid_list, 'img',
                                               config=dict(dim_size=chip_width),
                                               read_extern=False)
        nx.set_node_attributes(graph, 'framewidth', 3.0)
        #nx.set_node_attributes(graph, 'framecolor', pt.DARK_BLUE)
        nx.set_node_attributes(graph, 'shape', _dz(annot_nodes, ['rect']))
        nx.set_node_attributes(graph, 'image', _dz(annot_nodes, imgpath_list))

    def get_colored_edge_weights(infr, graph=None):
        # Update color and linewidth based on scores/weight
        if graph is None:
            graph = infr.graph
        edges = list(infr.graph.edges())
        edge2_weight = nx.get_edge_attributes(infr.graph, infr.CUT_WEIGHT_KEY)
        #edges = list(edge2_weight.keys())
        weights = np.array(ut.dict_take(edge2_weight, edges, np.nan))
        nan_idxs = []
        if len(weights) > 0:
            # give nans threshold value
            nan_idxs = np.where(np.isnan(weights))[0]
            weights[nan_idxs] = infr.thresh
        #weights = weights.compress(is_valid, axis=0)
        #edges = ut.compress(edges, is_valid)
        colors = infr.get_colored_weights(weights)
        #print('!! weights = %r' % (len(weights),))
        #print('!! edges = %r' % (len(edges),))
        #print('!! colors = %r' % (len(colors),))
        if len(nan_idxs) > 0:
            import plottool as pt
            for idx in nan_idxs:
                colors[idx] = pt.GRAY
        return edges, weights, colors

    def get_colored_weights(infr, weights):
        import plottool as pt
        #pt.rrrr()
        # cmap_ = 'viridis'
        # cmap_ = 'plasma'
        # cmap_ = pt.plt.cm.RdYlBu
        cmap_ = infr._get_cmap()
        # cmap_ = pt.plt.cm.RdYlBu
        #cmap_ = pt.plt.get_cmap(cmap_)
        weights[np.isnan(weights)] = infr.thresh
        #colors = pt.scores_to_color(weights, cmap_=cmap_, logscale=True)
        colors = pt.scores_to_color(weights, cmap_=cmap_, score_range=(0, 1),
                                    logscale=False, cmap_range=None)
        return colors

    @property
    def visual_edge_attrs(infr):
        """ all edge visual attrs """
        return infr.visual_edge_attrs_appearance + infr.visual_edge_attrs_space

    @property
    def visual_edge_attrs_appearance(infr):
        """ attrs that pertain to edge color and style """
        # picker doesnt really belong here
        return ['alpha', 'color', 'implicit', 'label', 'linestyle', 'lw',
                'pos', 'stroke', 'capstyle', 'hatch', 'style', 'sketch',
                'shadow', 'picker']

    @property
    def visual_edge_attrs_space(infr):
        """ attrs that pertain to edge positioning in a plot """
        return ['ctrl_pts', 'end_pt', 'head_lp', 'headlabel', 'lp', 'start_pt',
                'tail_lp', 'taillabel', 'zorder']

    @property
    def visual_node_attrs(infr):
        return ['color', 'framewidth', 'image', 'label',
                'pos', 'shape', 'size', 'height', 'width', 'zorder']

    def simplify_graph(infr, graph=None):
        if graph is None:
            graph = infr.graph
        s = graph.copy()
        ut.nx_delete_edge_attr(s, infr.visual_edge_attrs)
        ut.nx_delete_node_attr(s, infr.visual_node_attrs + ['pin'])
        return s

    def update_visual_attrs(infr, graph=None,
                            show_recent_review=True,
                            hide_reviewed_cuts=False,
                            hide_unreviewed_cuts=True,
                            # hide_unreviewed_inferred=True
                            ):
        if infr.verbose >= 3:
            print('[infr] update_visual_attrs')
        if graph is None:
            graph = infr.graph

        alpha_low = .5
        alpha_med = .9
        alpha_high = 1.0

        dark_background = graph.graph.get('dark_background', None)

        # Ensure we are starting from a clean slate
        ut.nx_delete_edge_attr(graph, infr.visual_edge_attrs_appearance)

        # Set annotation node labels
        node_to_aid = nx.get_node_attributes(graph, 'aid')
        node_to_nid = nx.get_node_attributes(graph, 'name_label')
        node_to_view = nx.get_node_attributes(graph, 'viewpoint')
        if node_to_view:
            annotnode_to_label = {
                node: 'aid=%r%s\nnid=%r' % (aid, node_to_view[node],
                                            node_to_nid[node])
                for node, aid in node_to_aid.items()
            }
        else:
            annotnode_to_label = {
                node: 'aid=%r\nnid=%r' % (aid, node_to_nid[node])
                for node, aid in node_to_aid.items()
            }
        nx.set_node_attributes(graph, 'label', annotnode_to_label)

        # NODE_COLOR: based on name_label
        ut.color_nodes(graph, labelattr='name_label', sat_adjust=-.4)

        # EDGES:
        # Grab different types of edges
        edges, edge_weights, edge_colors = infr.get_colored_edge_weights(graph)

        reviewed_states = nx.get_edge_attributes(graph, 'reviewed_state')
        nomatch_edges = [edge for edge, state in reviewed_states.items()
                         if state in {'nomatch'}]
        reviewed_edges = [edge for edge, state in reviewed_states.items()
                          if state in {'match', 'nomatch', 'notcomp'}]
        unreviewed_edges = ut.setdiff(edges, reviewed_edges)
        # comp_reviewed_edges = [edge for edge, state in
        #                        reviewed_states_full.items()
        #                        if state in {'match', 'nomatch'}]
        split_edges = [edge for edge, split in
                       nx.get_edge_attributes(graph, 'maybe_split').items()
                       if split]
        cut_edges = [edge for edge, cut in
                     nx.get_edge_attributes(graph, 'is_cut').items()
                     if cut]
        unreviewed_cut_edges = ut.setdiff(cut_edges, reviewed_edges)
        reviewed_cut_edges = ut.setdiff(cut_edges, unreviewed_cut_edges)
        edge_to_inferred_state = nx.get_edge_attributes(graph, 'inferred_state')
        uninferred_edges = [edge for edge, state in edge_to_inferred_state.items()
                            if state not in {'same', 'diff'}]
        inferred_edges = [edge for edge, state in edge_to_inferred_state.items()
                          if state in {'same', 'diff'}]
        dummy_edges = [edge for edge, flag in
                       nx.get_edge_attributes(graph, '_dummy_edge').items()
                       if flag]
        edge_to_timestamp = nx.get_edge_attributes(graph, 'review_timestamp')

        # EDGE_COLOR: based on edge_weight
        nx.set_edge_attributes(graph, 'color', _dz(edges, edge_colors))

        # LINE_WIDTH: based on review_state
        nx.set_edge_attributes(graph, 'linewidth', _dz(
            reviewed_edges, [5.0]))
        nx.set_edge_attributes(graph, 'linewidth', _dz(
            unreviewed_edges, [2.0]))

        # EDGE_STROKE: based on reviewed_state and maybe_split
        fg = pt.WHITE if dark_background else pt.BLACK
        nx.set_edge_attributes(graph, 'stroke', _dz(reviewed_edges, [
            {'linewidth': 3, 'foreground': fg}]))
        nx.set_edge_attributes(graph, 'stroke', _dz(split_edges, [
            {'linewidth': 5, 'foreground': pt.ORANGE}]))

        # Are cuts visible or invisible?
        nx.set_edge_attributes(graph, 'implicit', _dz(cut_edges, [True]))
        nx.set_edge_attributes(graph, 'linestyle', _dz(cut_edges, ['dashed']))
        nx.set_edge_attributes(graph, 'alpha', _dz(cut_edges, [alpha_med]))

        nx.set_edge_attributes(graph, 'implicit', _dz(uninferred_edges, [True]))

        # No-matching edges should not impose a constraint on the graph layout
        nx.set_edge_attributes(graph, 'implicit', _dz(nomatch_edges, [True]))
        nx.set_edge_attributes(graph, 'alpha', _dz(nomatch_edges, [alpha_med]))

        # Ensure reviewed edges are visible
        nx.set_edge_attributes(graph, 'alpha', _dz(reviewed_edges,
                                                   [alpha_high]))

        # SKETCH: based on inferred_edges
        # Make inferred edges wavy
        nx.set_edge_attributes(
            graph, 'sketch', _dz(inferred_edges, [
                dict(scale=10.0, length=64.0, randomness=None)]
                # dict(scale=3.0, length=18.0, randomness=None)]
            ))

        # Make dummy edges more transparent
        nx.set_edge_attributes(graph, 'alpha', _dz(dummy_edges, [alpha_low]))

        # SHADOW: based on review_timestamp
        # Increase visibility of nodes with the most recently changed timestamp
        if edge_to_timestamp:
            timestamps = list(edge_to_timestamp.values())
            recent_idxs = ut.where(ut.equal([max(timestamps)], timestamps))
            recent_edges = ut.take(list(edge_to_timestamp.keys()), recent_idxs)
            # TODO: add photoshop-like parameters like
            # spread and size. offset is the same as angle and distance.
            nx.set_edge_attributes(graph, 'shadow', _dz(recent_edges, [{
                'rho': .3,
                'alpha': .3,
                'shadow_color': 'w' if dark_background else 'k',
                # 'offset': (2, -2),
                'offset': (0, 0),
                'scale': 2.0,
                # 'offset': (4, -4)
            }]))

        # Z_ORDER: make sure nodes are on top
        nodes = list(graph.nodes())
        nx.set_node_attributes(graph, 'zorder', _dz(nodes, [10]))
        nx.set_edge_attributes(graph, 'zorder', _dz(edges, [0]))
        nx.set_edge_attributes(graph, 'picker', _dz(edges, [10]))

        # VISIBILITY: Set visibility of edges based on arguments
        # if show_unreviewed_inferred:
        #     # Infered edges are hidden
        #     nx.set_edge_attributes(
        #         graph, 'style', _dz(inferred_edges, ['invis']))

        # if only_reviewed:
        #     # only reviewed edges contribute
        #     nx.set_edge_attributes(graph, 'implicit',
        #                            _dz(unreviewed_edges, [True]))
        #     nx.set_edge_attributes(graph, 'alpha',
        #                            _dz(unreviewed_edges, [alpha_med]))
        #     nx.set_edge_attributes(graph, 'style',
        #                            _dz(unreviewed_edges, ['invis']))

        if hide_unreviewed_cuts:
            nx.set_edge_attributes(graph, 'style', _dz(
                unreviewed_cut_edges, ['invis']))
        if hide_reviewed_cuts:
            nx.set_edge_attributes(graph, 'style', _dz(
                reviewed_cut_edges, ['invis']))

        if show_recent_review and edge_to_timestamp:
            # Always show the most recent review (remove setting of invis)
            nx.set_edge_attributes(graph, 'style',
                                   _dz(recent_edges, ['']))

        # LAYOUT: update the positioning layout
        layoutkw = dict(prog='neato', splines='spline', sep=10 / 72)
        pt.nx_agraph_layout(graph, inplace=True, **layoutkw)

    def show_graph(infr, use_image=False, with_colorbar=False, **kwargs):
        kwargs['fontsize'] = kwargs.get('fontsize', 8)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            default_update_kw = ut.get_func_kwargs(infr.update_visual_attrs)
            update_kw = ut.update_existing(default_update_kw, kwargs)
            infr.update_visual_attrs(**update_kw)
            graph = infr.graph
            plotinfo = pt.show_nx(graph, layout='custom', as_directed=False,
                                  modify_ax=False, use_image=use_image, verbose=0,
                                  **kwargs)
            plotinfo  # NOQA
            pt.zoom_factory()
            pt.pan_factory(pt.gca())

        if with_colorbar:
            # Draw a colorbar
            _normal_ticks = np.linspace(0, 1, num=11)
            _normal_scores = np.linspace(0, 1, num=500)
            _normal_colors = infr.get_colored_weights(_normal_scores)
            cb = pt.colorbar(_normal_scores, _normal_colors, lbl='weights',
                             ticklabels=_normal_ticks)

            # point to threshold location
            if infr.thresh is not None:
                xy = (1, infr.thresh)
                xytext = (2.5, .3 if infr.thresh < .5 else .7)
                cb.ax.annotate('threshold', xy=xy, xytext=xytext,
                               arrowprops=dict(
                                   alpha=.5, fc="0.6",
                                   connectionstyle="angle3,angleA=90,angleB=0"),)

        # infr.graph
        if infr.graph.graph.get('dark_background', None):
            pt.dark_background(force=True)

    show = show_graph
