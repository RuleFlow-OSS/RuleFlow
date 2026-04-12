"""
This plugin provides access to various analysis features such as causal networks and overall evolution metrics.
"""
# Textual Imports
from textual.widgets import (Collapsible, TabPane, Input, Checkbox, SelectionList,
                             Button, Label, Sparkline, Select, DataTable)
from textual.widget import Widget
from textual.containers import VerticalScroll
from textual.widgets.selection_list import Selection

# Standard Imports
from typing import Iterator
from studio.model import Plugin
from core.graph import EventCausalityGraph
from core.numlib import str_to_num, INF
from studio.config import USER_DATA_DIR_PATH
from pyvis.network import Network
import networkx as nx
from statistics import fmean
import math


class P(Plugin):
    def on_initialized(self) -> None:
        self.name = 'analysis'

        # tools
        self._causal_graph: EventCausalityGraph | None = None

        # signals
        self.view.sig_button_pressed.connect(self.handle_button_press)

    def controls(self) -> Iterator[Widget]:
        with Collapsible(title='Causal Network', collapsed=False):
            yield Button('Build Graph', id='build-graph', variant="primary")
            self.causal_network_event_range = Input(':32')
            self.causal_network_event_range.border_title = 'Event Range'
            yield self.causal_network_event_range
            self.collapse_edges = Checkbox('Collapse Edges')
            yield self.collapse_edges
            yield Label("\nPersistence")
            self.export_format = Select(
                [("Gephi", 0), ("GraphML", 1), ("Sparse6", 2), ("Graph6", 3), ("GML", 4), ("Adjacency List", 5), ("Multiline Adjacency", 6)],
                allow_blank=False
            )
            yield self.export_format
            yield Button('Export as Format', id='export-graph')

        with Collapsible(title='VisJS Viewer', collapsed=False):
            yield Button('View Graph', id='view-graph', variant="primary")
            self.vis_html_path = Input(value="auto", placeholder="e.g., auto or /home/test.html")
            self.vis_html_path.border_title = 'HTML File Path'
            yield self.vis_html_path
            self.vis_open_browser = Checkbox('Open Browser', value=True)
            yield self.vis_open_browser

            yield Label("\nCanvas Settings")
            self.vis_height = Input(value="800px", placeholder="e.g., 800px")
            self.vis_height.border_title = 'Height'
            yield self.vis_height
            self.vis_width = Input(value="100%", placeholder="e.g., 100%")
            self.vis_width.border_title = 'Width'
            yield self.vis_width
            self.vis_bgcolor = Input(value="#ffffff", placeholder="e.g., #ffffff")
            self.vis_bgcolor.border_title = 'Background Color'
            yield self.vis_bgcolor
            self.vis_font_color = Input(value="", placeholder="e.g., #000000")
            self.vis_font_color.border_title = 'Font Color'
            yield self.vis_font_color
            self.vis_heading = Input(value="")
            self.vis_heading.border_title = 'Graph Heading'
            yield self.vis_heading
            self.vis_cdn = Select(
                [("Remote", "remote"), ("Local", "local"), ("Inline", "in_line")],
                value="remote",
                prompt="CDN Resources",
                allow_blank=False
            )
            yield self.vis_cdn

            yield Label("\nOptions")
            self.vis_toggles = SelectionList(
                Selection("Directed Edges", "directed", True),
                Selection("Neighborhood Highlight", "neighborhood", True),
                Selection("Select Menu", "select_menu", False),
                Selection("Filter Menu", "filter_menu", False),
                Selection("Hierarchy Layout", "layout", False),
            )
            yield self.vis_toggles
            yield Label("\nUI Filters")
            self.show_buttons = Checkbox('Show Buttons', value=False)
            yield self.show_buttons
            self.vis_buttons_filter = SelectionList(
                Selection("All", "all", False),
                Selection("Nodes", "nodes", True),
                Selection("Edges", "edges", True),
                Selection("Layout", "layout", False),
                Selection("Interaction", "interaction", True),
                Selection("Manipulation", "manipulation", False),
                Selection("Physics", "physics", True),
                Selection("Selection", "selection", False),
                Selection("Renderer", "renderer", False)
            )
            yield self.vis_buttons_filter

        with Collapsible(title='Causal Distribution'):
            yield Label('Summery Function:')
            self.summary_function = Select([('Min', 0), ('Max', 1), ('Mean', 2)], allow_blank=False)
            yield self.summary_function
            self.evolution_metrics_event_range = Input(':100')
            self.evolution_metrics_event_range.border_title = 'Event Range'
            yield self.evolution_metrics_event_range
            yield Button('Calculate', id='calculate-metrics', variant="primary")
        yield Label()

    def handle_button_press(self, e: Button.Pressed):
        _id: str = e.button.id
        if _id == 'build-graph':
            self._update_causal_graph()
        elif _id == 'export-graph':
            self._export_as_format()
        elif _id == 'view-graph':
            self._open_vis_js_viewer()
        elif _id == 'calculate-metrics':
            self._update_evolution_metrics()

    def _open_vis_js_viewer(self) -> None:
        if not self._causal_graph:
            self.view.notify('No graph has been built yet!', severity='error')
            return

        G: nx.MultiDiGraph = self._causal_graph

        # Get the list of selected internal string values
        selected = self.vis_toggles.selected

        # Parse text inputs
        f_color = self.vis_font_color.value.strip()
        f_color_parsed = f_color if f_color else False

        # Layout requires True or None, so we map it from the selection list
        layout_parsed = True if "layout" in selected else None

        # Instantiate the VisJS Network
        net = Network(
            height=self.vis_height.value.strip() or "800px",
            width=self.vis_width.value.strip() or "100%",
            directed="directed" in selected,
            neighborhood_highlight="neighborhood" in selected,
            select_menu="select_menu" in selected,
            filter_menu="filter_menu" in selected,
            bgcolor=self.vis_bgcolor.value.strip() or "#ffffff",
            font_color=f_color_parsed,
            layout=layout_parsed,
            heading=self.vis_heading.value.strip(),
            cdn_resources=self.vis_cdn.value
        )

        # Apply the show_buttons filters based on the selection list
        if self.show_buttons.value:
            filtered_buttons = self.vis_buttons_filter.selected
            if "all" in filtered_buttons:
                net.show_buttons(filter_=True)
            else:
                net.show_buttons(filter_=filtered_buttons)

        # Ingest and Render
        net.from_nx(G)
        try:
            if self.vis_html_path.value == 'auto':
                html_path = str(USER_DATA_DIR_PATH.joinpath('temp_vis_js.html'))
            else:
                html_path = self.vis_html_path.value
                if not html_path.endswith('.html'):
                    html_path += '.html'
            net.write_html(html_path, open_browser=self.vis_open_browser.value)
            self.view.notify("VisJS graph launched in your browser!")
        except Exception as e:
            self.view.notify(f"Failed to open viewer: {str(e)}", severity="error")

    def _export_as_format(self):
        if not self._causal_graph:
            self.view.notify('No graph has been built yet!', severity='error')
            return

        funcs = [nx.write_gexf, nx.write_graphml, nx.write_sparse6, nx.write_graph6,
                 nx.write_gml, nx.write_adjlist, nx.write_multiline_adjlist]
        stems = ['.gexf', '.graphml', '.sparse6', '.graph6', '.gml', '.adjlist', '.multi_adjlist']
        stem: str = stems[self.export_format.value]
        path: str = str(
            self.model.project_path.joinpath(
                self.model.flow_path.name + f'_at_{self.causal_network_event_range.value.replace(':', '_')}' + stem
            )
        )
        try:
            funcs[self.export_format.value](self._causal_graph, path)
            self.view.notify(f'Successfully exported at "{path}"')
        except Exception as e:
            self.view.notify(f"Failed to export graph: {str(e)}", severity="error")

    def panel(self) -> TabPane | None:
        # ==== network metrics ====
        self.causal_graph_metrics = DataTable(show_cursor=False, zebra_stripes=True)
        self.causal_graph_metrics.add_columns(('Metric', 'metric'), ('Value', 'value'))
        for i, m in enumerate(('Edge-Node Ratio', 'Network Density',
                               'Longest DAG Path', 'Degree Assortativity Coefficient',
                               'Flow Hierarchy')):
            self.causal_graph_metrics.add_row(m, 'N/A', key=str(i))

        # ==== Causal Distributions ====
        self.distance_distribution = Sparkline()
        self.connected_abs_distribution = Sparkline()
        self.connected_set_distribution = Sparkline()
        return TabPane(
            self.name.title(),
            VerticalScroll(
                Collapsible(
                    self.causal_graph_metrics,
                    title='Causal Network Metrics', collapsed=False
                ),
                Collapsible(
                    Label('[bold] Causal Distance [/bold]'),
                    self.distance_distribution,
                    Label('\n[bold] Connected Total [/bold]'),
                    self.connected_abs_distribution,
                    Label('\n[bold] Connected Unique [/bold]'),
                    self.connected_set_distribution,
                    title='Causal Distributions', collapsed=True
                ),
            )
        )

    def _update_causal_graph(self):
        # get the event range
        rs: list[str] = self.causal_network_event_range.value.split(':')
        if len(rs) == 2: rs.append('')  # it must be 3 things
        r = (
            int(rs[0]) if rs[0] else 0,
            str_to_num(rs[1]) if rs[1] else INF,
            abs(int(rs[2])) if rs[2] else 1
        )
        self._causal_graph = EventCausalityGraph().build(self.model.flow, r, self.collapse_edges.value)
        self._update_causal_metrics_table(self._causal_graph)

    def _update_causal_metrics_table(self, g: EventCausalityGraph) -> None:
        """Calculates causal graph metrics and updates the Textual DataTable."""
        if g.number_of_nodes() == 0:
            for i in range(len(self.causal_graph_metrics.rows)):
                self.causal_graph_metrics.update_cell(str(i), "value", "N/A")
            return
        try:
            edge_node_ratio = g.number_of_edges() / g.number_of_nodes()
            edge_node_ratio_str = f"{edge_node_ratio:.3f}"
        except ZeroDivisionError: edge_node_ratio_str = "0.000"
        density = nx.density(g)
        density_str = f"{density:.5f}"
        try:
            depth = nx.dag_longest_path_length(g)
            depth_str = str(depth)
        except nx.NetworkXUnfeasible: depth_str = "Cycle Detected"
        try:
            assortativity = nx.degree_assortativity_coefficient(g)
            if math.isnan(assortativity):
                assort_str = "0.000"
            else:
                assort_str = f"{assortativity:.4f}"
        except Exception:  assort_str = "0.000"
        try:
            flow = nx.flow_hierarchy(g)
            flow_str = f"{flow:.4f}"
        except ZeroDivisionError: flow_str = "0.000"

        # update the cells
        for i, s in enumerate((edge_node_ratio_str, density_str, depth_str, assort_str, flow_str)):
            self.causal_graph_metrics.update_cell(str(i), "value", s)

    def _update_evolution_metrics(self):
        # get the event range
        rs: list[str] = self.evolution_metrics_event_range.value.split(':')
        if len(rs) == 2: rs.append('')  # it must be 3 things
        a, b, c = (
            int(rs[0]) if rs[0] else 0,
            str_to_num(rs[1]) if rs[1] else INF,
            abs(int(rs[2])) if rs[2] else 1
        )

        # get summary function
        f = (min, max, fmean)[self.summary_function.value]
        self.distance_distribution.summary_function = f
        self.connected_abs_distribution.summary_function = f
        self.connected_set_distribution.summary_function = f

        # calculate the data to show
        causal_distance_data: list[int] = []
        connected_abs_distance_data: list[int] = []
        connected_set_distance_data: list[int] = []
        for event in self.model.flow.events[a:b+(1 if b > 0 else 0):c]:
            causal_distance_data.append(event.causal_distance_to_creation)
            connected_abs_distance_data.append(len(_:=tuple(event.causally_connected_events)))
            connected_set_distance_data.append(len(set(_)))
        self.distance_distribution.data = causal_distance_data
        self.connected_abs_distribution.data = connected_abs_distance_data
        self.connected_set_distribution.data = connected_set_distance_data


plugin = P()
