from copy import deepcopy
from collections import defaultdict
from topology_shape_metrics.flownet import Flow_net
import networkx as nx

class Compaction:
    '''
    Assign minimum lengths to the segments of the edges of the orthogonal representation.
    Never reverse ortho in this class.
    '''

    def __init__(self, ortho):
        self.ortho = ortho
        if ortho.flow_network.cost == 0:
            # no bend point, not modify planar and flow_dict
            self.planar = ortho.planar
            self.flow_dict = ortho.flow_dict
        else:
            self.planar = ortho.planar.copy()
            self.flow_dict = deepcopy(ortho.flow_dict)

        self.bend_point_processor()
        halfedge_side = self.face_side_processor()
        halfedge_length = self.tidy_rectangle_compaction(halfedge_side)
        self.pos = self.layout(halfedge_side, halfedge_length)

    def bend_point_processor(self):
        '''Create dummy nodes for bends.
        '''
        bends = {}  # left to right
        for he in self.planar.dcel.half_edges.values():
            lf, rf = he.twin.inc, he.inc
            flow = self.flow_dict[lf.id][rf.id][he.id]
            if flow > 0:
                bends[he] = flow

        idx = 0
        # (u, v) -> (u, bend0, bend1, ..., v)
        for he, num_bends in bends.items():
            # Q: what if there are bends on both (u, v) and (v, u)?
            # A: Impossible, not a min cost
            u, v = he.get_points()
            lf_id, rf_id = he.twin.inc.id, he.inc.id

            self.planar.G.remove_edge(u, v)
            # use ('bend', idx) to represent bend node
            self.flow_dict[u][rf_id][u,
                                        ('bend', idx)] = self.flow_dict[u][rf_id].pop((u, v))

            for i in range(num_bends):
                cur_node = ('bend', idx)
                pre_node = ('bend', idx-1) if i > 0 else u
                nxt_node = ('bend', idx+1) if i < num_bends - 1 else v
                self.planar.G.add_edge(pre_node, cur_node)
                self.planar.dcel.add_node_between(
                    pre_node, v, cur_node
                )
                self.flow_dict.setdefault(cur_node, {}).setdefault(
                    lf_id, {})[cur_node, pre_node] = 1
                self.flow_dict.setdefault(cur_node, {}).setdefault(
                    rf_id, {})[cur_node, nxt_node] = 3
                idx += 1

            self.flow_dict[v][lf_id][v,
                                     ('bend', idx-1)] = self.flow_dict[v][lf_id].pop((v, u))
            self.planar.G.add_edge(('bend', idx-1), v)

    def face_side_processor(self):
        '''Associating edges with face sides.
        '''

        def update_face_edge(halfedge_side, face, base):
            for he in face.surround_half_edges():
                halfedge_side[he] = (halfedge_side[he] + base) % 4

        halfedge_side = {}
        for face in self.planar.dcel.faces.values():
            # set edges' side in internal faces independently at first
            side = 0
            for he in face.surround_half_edges():
                halfedge_side[he] = side
                end_angle = self.flow_dict[he.succ.ori.id][face.id][he.succ.id]
                if end_angle == 1:
                    # turn right in internal face or turn left in external face
                    side = (side + 1) % 4
                elif end_angle == 3:
                    side = (side + 3) % 4
                elif end_angle == 4:  # a single edge
                    side = (side + 2) % 4

        # update other face's edge side based on ext_face's edge side
        faces_dfs = list(self.planar.dfs_face_order())

        # all faces in dfs order
        has_updated = {faces_dfs[0]}
        for face in faces_dfs[1:]:
            # at least one twin edge has been set
            for he in face.surround_half_edges():
                lf = he.twin.inc
                if lf in has_updated:  # neighbor face has been updated
                    # the edge that has been updated
                    l_side = halfedge_side[he.twin]
                    r_side = halfedge_side[he]  # side of u, v in face
                    update_face_edge(
                        halfedge_side, face, (l_side + 2) % 4 - r_side)
                    has_updated.add(face)
                    break
        return halfedge_side

    def tidy_rectangle_compaction(self, halfedge_side):
        '''
        Doing the compaction of TSM algorithm.
        Compute every edge's length, and store them in self.planar.G.edges[u, v]['len']
        '''
        def build_flow(target_side):
            hv_flow = Flow_net()
            for he, side in halfedge_side.items():
                if side == target_side:
                    lf, rf = he.twin.inc, he.inc
                    lf_id = lf.id
                    rf_id = rf.id if not rf.is_external else ('face', 'end')
                    hv_flow.add_edge(lf_id, rf_id, he.id)
            return hv_flow

        def solve(hv_flow, source, sink):
            if not hv_flow:
                return {}
            for node in hv_flow:
                hv_flow.nodes[node]['demand'] = 0
            hv_flow.nodes[source]['demand'] = -2**32
            hv_flow.nodes[sink]['demand'] = 2**32
            for lf_id, rf_id, he_id in hv_flow.edges:
                # what if selfloop?
                hv_flow.edges[lf_id, rf_id, he_id]['weight'] = 1
                hv_flow.edges[lf_id, rf_id, he_id]['lowerbound'] = 1
                hv_flow.edges[lf_id, rf_id, he_id]['capacity'] = 2**32
            hv_flow.add_edge(source, sink, 'extend_edge',
                             weight=0, lowerbound=0, capacity=2**32)

            # selfloop，avoid inner edge longer than border
            # for u, _ in hv_flow.selfloop_edges():
            #     in_nodes = [v for v, _ in hv_flow.in_edges(u)]
            #     assert in_nodes
            #     delta = sum(hv_flow[v][u]['lowerbound'] for v in in_nodes) - hv_flow[u][u]['count']
            #     if delta < 0:
            #         hv_flow.edges[in_nodes[0]][u]['lowerbound'] += -delta
            return hv_flow.min_cost_flow()

        hor_flow = build_flow(1)  # up -> bottom
        ver_flow = build_flow(0)  # left -> right

        hor_flow_dict = solve(hor_flow, self.planar.ext_face.id, ('face', 'end'))
        ver_flow_dict = solve(ver_flow, self.planar.ext_face.id, ('face', 'end'))

        halfedge_length = {}
        for he in self.planar.dcel.half_edges.values():
            if halfedge_side[he] in (0, 1):
                side = halfedge_side[he]

                rf = he.inc
                rf_id = ('face', 'end') if rf.is_external else rf.id
                lf_id = he.twin.inc.id

                if side == 0:
                    hv_flow_dict = ver_flow_dict
                elif side == 1:
                    hv_flow_dict = hor_flow_dict

                length = hv_flow_dict[lf_id][rf_id][he.id]
                halfedge_length[he] = length
                halfedge_length[he.twin] = length

        return halfedge_length

    def layout(self, halfedge_side, halfedge_length):
        pos = {}
        for face in self.planar.dfs_face_order():
            for start_he in face.surround_half_edges():
                if not pos:
                    pos[start_he.ori.id] = (0, 0)  # initial point
                if start_he.ori.id in pos:  # has found a start point
                    for he in start_he.traverse():
                        u, v = he.get_points()
                        side = halfedge_side[he]
                        length = halfedge_length[he]
                        x, y = pos[u]
                        if side == 1:
                            pos[v] = (x + length, y)
                        elif side == 3:
                            pos[v] = (x - length, y)
                        elif side == 0:
                            pos[v] = (x, y + length)
                        else:  # side == 2
                            pos[v] = (x, y - length)
                    break
        return pos


