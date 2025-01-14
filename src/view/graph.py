from PyQt5 import QtWidgets, uic, QtCore, QtGui
from src.view import ui, CMAP
import os
import copy
from src import UI_DIR, IMAGES_STACK, _IMAGES_STACK
import numpy as np


class Link(QtWidgets.QGraphicsPathItem):
    """
    graphic line between two graphic points

    Parameters
    ----------
    junction1/junction2: Junction
        the two points to link

    """
    def __init__(self, junction1, junction2):
        super().__init__()
        self.j1, self.j2 = junction1, junction2
        self.setZValue(-1)
        line_width = 2
        color = QtGui.QColor(0, 150, 0)
        self.setPen(QtGui.QPen(color, line_width))

        # set curve point positions
        self._path = QtGui.QPainterPath(self.j1.pos())
        self._path.cubicTo(0, 0, 0, 0, 0, 0)
        self.updateElement(0, self.j1.pos())
        self.updateElement(1, self.j2.pos())

        self.j1.links.append((self, 0))
        self.j2.links.append((self, 1))
        self.setPath(self._path)

        self.j1.updateLinkPos()
        self.j2.updateLinkPos()

    def updateElement(self, index, pos):
        """
        update the position of one end of line

        Parameters
        ----------
        index: {0, 1}
            specified one of the two end of line
        pos: QtCore.QPoint
            new position for the end of line

        """
        if self.j1.node.graph.direction == 'horizontal':
            nx, ny = 30, 0
        elif self.j1.node.graph.direction == 'vertical':
            nx, ny = 0, 30

        if index == 0:
            self._path.setElementPositionAt(0, pos.x(), pos.y())
            self._path.setElementPositionAt(1, pos.x()+nx, pos.y()+ny)
        elif index == 1:
            self._path.setElementPositionAt(2, pos.x()-nx, pos.y()-ny)
            self._path.setElementPositionAt(3, pos.x(), pos.y())

        self.setPath(self._path)


class Junction(QtWidgets.QGraphicsPolygonItem):
    """
    graphic point

    Parameters
    ----------
    node: Node

    """
    def __init__(self, node, hide=False):
        super(Junction, self).__init__(node.handle)
        self.node = node
        if not hide:
            self.initShape()

        self.links = []
        self.setZValue(1)

    def initShape(self):
        size = 5
        color = QtGui.QColor(0, 150, 0)
        if self.node.graph.direction == 'horizontal':
            points = [QtCore.QPoint(0, 0),
                      QtCore.QPoint(-size, size),
                      QtCore.QPoint(-size, -size)]
        if self.node.graph.direction == 'vertical':
            points = [QtCore.QPoint(0, 0),
                      QtCore.QPoint(-size, -size),
                      QtCore.QPoint(size, -size)]
        self.setPolygon(QtGui.QPolygonF(points))
        self.setBrush(QtGui.QBrush(color))
        self.setPen(QtGui.QPen(color))

    def updateLinkPos(self):
        for link, index in self.links:
            link.updateElement(index, self.node.pos()+self.pos())


class Node(ui.QViewWidget):
    """
    movable widget inside the graph associated to a pipeline's step

    Parameters
    ----------
    graph: Graph
    type: str
        type of node associated to specific widget and functions
    name: str
        unique name
    parents: list of Node, default=[]
        nodes whose outputs are self input
    position: tuple, default=(0,0)
        position of the node in the graphic view

    """
    rightClicked = QtCore.pyqtSignal(int)

    def __init__(self, graph, type, name, parents=[], position=(0, 0)):
        super().__init__(os.path.join(UI_DIR, "Node.ui"))
        self.graph = graph
        self.type = type
        self.name = name
        self.button.setText(name)
        self.snap.wheelEvent = self.snapWheelEvent
        self.snap.mouseDoubleClickEvent = self.snapMouseDoubleClickEvent
        self.snap.mousePressEvent = self.snapMousePressEvent
        self.snap.setVisible(False)

        self.positionChanged.connect(self.moveChilds)
        self.sizeChanged.connect(self.updateSnap)
        self.sizeChanged.connect(self.updateHeight)

        self.current_branch = []
        self.childs = []
        self.parents = parents
        self.current_slice = None
        self.cmap = 'rednan'
        self.ctable = None
        self.snap_axis = 0
        self.junctions = []

    def updateHeight(self):
        """
        resize widget to its minimum height
        """
        self.resize(self.width(), self.minimumHeight())

    def moveChilds(self):
        """
        if shift is holded, move node childs with it
        """
        if self.graph.holdShift:
            if self.state == 'pressed':
                self.state = 'isMoving'
                self.updateCurrentBranch()
            if self.state == 'isMoving':
                delta = self.pos() - self.current_position
                self.current_position = self.pos()
                for child in self.current_branch:
                    child.moveBy(delta.x(), delta.y())

    def mousePressEvent(self, event=None):
        self.handle.setSelected(True)

    def mouseReleaseEvent(self, event=None):
        if not self.graph.holdCtrl:
            self.handle.setSelected(False)

    def addJunction(self, type):
        """
        create a junction to fix link

        Parameters
        ----------
        type: {'out', 'in'}
            type of junction, if 'out' the junction will be hidden
            the type influence the relative position of the junction in the node

        Return
        ------
        junction: Junction
        """
        junction = Junction(self, hide=type == 'out')
        self.positionChanged.connect(junction.updateLinkPos)
        self.sizeChanged.connect(lambda: junction.setPos(*self.getJunctionRelativePosition(type)))
        self.sizeChanged.connect(junction.updateLinkPos)
        self.sizeChanged.emit()
        self.junctions.append(junction)
        return junction

    def getJunctionRelativePosition(self, type='out'):
        """
        get the relative position of the junction in the node

        Parameters
        ----------
        type: {'out', 'in'}, default='out'
            type of the node

        Return
        ------
        x, y: two floats
            relative position of the junction
        """
        if self.graph.direction == 'horizontal':  # left to right
            if type == 'out':
                return self.width(), self.height()/2
            elif type == 'in':
                return 0, self.height()/2
        elif self.graph.direction == 'vertical':  # top to bottom
            if type == 'out':
                return self.width()/2, self.height()
            elif type == 'in':
                return self.width()/2, 0

    def delete(self):
        """
        delete itself and all related graphic items (links and junctions)
        """
        for j in self.junctions:
            for l1, _ in j.links:
                self.graph.scene.removeItem(l1)
            self.graph.scene.removeItem(j)
        self.graph.scene.removeItem(self.handle)
        self.proxy.deleteLater()
        self.deleteLater()

    def snapWheelEvent(self, event):
        """
        update image slice on scroll wheel above image view
        """
        if self.current_slice is not None:
            step = 1
            if event.angleDelta().y() > 0:
                self.current_slice += step
            else:
                self.current_slice -= step
            self.updateSnap()

    def snapMouseDoubleClickEvent(self, event):
        """
        update image axis on double click above image view
        """
        if self.snap_axis == 2:
            self.snap_axis = 0
        else:
            self.snap_axis += 1
        self.updateSnap()

    def snapMousePressEvent(self, event):
        """
        update pixel value and position labels when clicking snap view
        """
        # set ratio between image and qpixmap
        if self.name not in _IMAGES_STACK:
            return
        ratio = _IMAGES_STACK[self.name].shape[int(self.snap_axis == 0)] / self.snap.width()
        # get click position
        click_pos = np.array([event.pos().y(), event.pos().x()])
        # define position in image
        true_pos = np.rint(click_pos * ratio).astype(int)
        x, y, z = np.insert(true_pos, self.snap_axis, self.current_slice)
        # update labels with pixel value and position
        self.value.setText(str(_IMAGES_STACK[self.name][x, y, z])+" ")
        self.position.setText("{0} {1} {2}".format(x, y, z))

    def enterEvent(self, event):
        """
        disable graphics view scrolling when entering node
        """
        self.graph.setEnabledScroll(False)
        self.graph.focus = self
        return super(Node, self).enterEvent(event)

    def leaveEvent(self, event):
        """
        enable graphics view scrolling when leaving node
        """
        self.graph.setEnabledScroll(True)
        self.graph.focus = None
        return super(Node, self).leaveEvent(event)

    def getChilds(self):
        """
        get all children

        Return
        ------
        childs: list of Node

        """
        childs = self.childs
        for child in self.childs:
            childs += child.getChilds()
        return childs

    def updateCurrentBranch(self):
        """
        update the current branch as a unique list of nodes
        """
        self.current_branch = set(self.getChilds())

    def getScaledColorTable(self, im):
        """
        compute the color table scaled between min and max of image pixel values

        Parameters
        ----------
        im: 2d/ 3d numpy array

        Return
        ------
        ctable: list of qRgb
            list of all colors associated to a pixel value
            first color for pixel=0, second color for pixel=1, ...

        """
        if self.ctable is None:
            values = np.linspace(0, 255, int(np.nanmax(im)-np.nanmin(im)+1)).astype(int)
            self.ctable = [QtGui.qRgb(i, i, i) for i in values]
        return self.ctable

    def updateSnap(self, sync=True):
        """
        update image slice in snap view

        Parameters
        ----------
        sync: bool, default=True
            if True, update the children and parents image view
            to the current slice recursively

        """
        if self.name not in IMAGES_STACK:
            return
        self.snap.setVisible(True)

        im = IMAGES_STACK[self.name]
        s = im.shape[self.snap_axis]

        # set current slice
        if self.current_slice is None:
            self.current_slice = int(s / 2)
        elif self.current_slice < 0:
            self.current_slice = 0
        elif self.current_slice >= s:
            self.current_slice = s-1

        # snap axis slice
        if self.snap_axis == 0:
            im_slice = im[self.current_slice].copy()
            _, h, w = im.shape
        elif self.snap_axis == 1:
            im_slice = im[:, self.current_slice].copy()
            h, _, w = im.shape
        elif self.snap_axis == 2:
            im_slice = im[:, :, self.current_slice].copy()
            h, w, _ = im.shape

        # define qimage
        qim = QtGui.QImage(im_slice, w, h, w, QtGui.QImage.Format_Indexed8)
        qim.setColorTable(CMAP[self.cmap])

        # scale pixmap to qlabel size
        pixmap = QtGui.QPixmap(qim)
        pixmap = pixmap.scaled(self.snap.width(), self.snap.width(),
                               QtCore.Qt.KeepAspectRatio,
                               QtCore.Qt.FastTransformation)

        self.snap.setPixmap(pixmap)
        self.snap.update()

        # synchronize parents and children
        if sync:
            for node in self.childs+self.parents:
                if node.current_slice != self.current_slice:
                    node.current_slice = self.current_slice
                    node.updateSnap(sync)
                elif node.snap_axis != self.snap_axis:
                    node.snap_axis = self.snap_axis
                    node.updateSnap(sync)


class Graph(QtWidgets.QWidget):
    """
    widget containing a view to display a tree-like architecture with nodes
    and branches

    Parameters
    ----------
    mainwin: MainWindow
        QMainWindow where the graph is displayed
    direction: {'horizontal', 'vertical'}, default='horizontal'
        direction of the pipeline;
        horizontal is left to right, vertical is top to bottom

    """
    nodeClicked = QtCore.pyqtSignal(Node)

    def __init__(self, mainwin, direction='horizontal'):
        super().__init__()
        self.mainwin = mainwin
        self.direction = direction
        uic.loadUi(os.path.join(UI_DIR, "Graph.ui"), self)
        self.setWindowState(QtCore.Qt.WindowMaximized)
        self.scene = QtWidgets.QGraphicsScene()
        self.view.setRenderHint(QtGui.QPainter.Antialiasing)
        self.view.setScene(self.scene)
        self.view.contextMenuEvent = lambda e: self.openMenu()

        self.installEventFilter(self)
        self.holdShift = False
        self.holdCtrl = False
        self._mouse_position = QtCore.QPoint(0, 0)
        self.nodes = {}
        self.settings = {}
        self.focus = None

    def bind(self, parent, child):
        """
        create a link between a parent and a child node

        Parameters
        ----------
        parent, child: Node
            nodes to visually bind
        """
        jout = parent.addJunction('out')
        jin = child.addJunction('in')
        link = Link(jout, jin)
        self.scene.addItem(link)

    def setEnabledScroll(self, enable_scroll=True):
        """
        enable/disable view scrolling

        Parameters
        ----------
        enable_scroll: bool, default True
        """
        self.view.verticalScrollBar().setEnabled(enable_scroll)
        self.view.horizontalScrollBar().setEnabled(enable_scroll)

    def getSelectedNodes(self):
        """
        get all selected nodes (with ctrl+click shortcut)

        Return
        ------
        result: list of Node
        """
        return [n for n in self.nodes.values() if n.handle.isSelected()]

    def eventFilter(self, obj, event):
        """
        manage keyboard shortcut and mouse events on graph view
        """
        if obj == self:
            if event.type() == QtCore.QEvent.Wheel:
                return True
            elif event.type() == QtCore.QEvent.KeyPress:
                if event.key() == QtCore.Qt.Key_Shift:
                    self.holdShift = True
                elif event.key() == QtCore.Qt.Key_Control:
                    self.holdCtrl = True
            elif event.type() == QtCore.QEvent.KeyRelease:
                if event.key() == QtCore.Qt.Key_Shift:
                    self.holdShift = False
                elif event.key() == QtCore.Qt.Key_Control:
                    self.holdCtrl = False
        return super(Graph, self).eventFilter(obj, event)

    def getUniqueName(self, name):
        """
        find an unused name by adding _n at the end of the name

        Parameters
        ----------
        name: str
            default non-unique name of the node

        Return
        ------
        new_name: str
            unique name for the node

        """
        i = 1
        new_name = copy.copy(name)
        while new_name in self.nodes:
            new_name = "{0}_{1}".format(name, i)
            i += 1
        return new_name

    def openMenu(self, node=None):
        """
        open menu on right-clic at clicked position

        Parameters
        ----------
        node: Node, default None
            if None open a menu with primary actions (load, ...)
            else open a menu with secondary actions (erosion, ...)

        """
        node = self.focus
        if node is None:
            acts = self.mainwin.menu['primary']
            nodes = []
        else:
            acts = self.mainwin.menu['secondary']
            nodes = [node]
        nodes += self.getSelectedNodes()
        nodes = list(set(nodes))

        def activate(action):
            type = action.text()
            if type == "rename":
                self.renameNode(node)
            elif type in ["delete", "delete all"]:
                self.deleteBranch(node)
            elif type == "empty":
                self.deleteBranch(node, childs_only=True)
            else:
                self.addNode(action.text(), nodes)
        menu = ui.menuFromDict(acts, activation_function=activate)
        pos = QtGui.QCursor.pos()
        self._mouse_position = self.view.mapToScene(self.view.mapFromGlobal(pos))
        menu.exec_(QtGui.QCursor.pos())

    def deleteBranch(self, parent, childs_only=False):
        """
        delete node, its children and the associated data recursively

        Parameters
        ----------
        parent: Node
        child_only: bool, default=False
            if True do not delete the parent node else delete parent and children

        """
        # delete children if has no other parent
        for child in parent.childs:
            child.parents.remove(parent)
            if len(child.parents) == 0:
                self.deleteBranch(child)
        # delete data
        if parent.name in IMAGES_STACK:
            del _IMAGES_STACK[parent.name]
            del IMAGES_STACK[parent.name]
        # remove node from parent children
        for p in parent.parents:
            p.childs.remove(parent)
        # delete node and links
        parent.delete()
        del self.nodes[parent.name]

    def restoreGraph(self, settings):
        """
        restore graph architecture

        Parameters
        ----------
        settings: dict
            the dict-like description of the graph

        """
        for k, values in settings.items():
            self.addNode(**values)

    def addNode(self, type, parents=[]):
        """
        create a Node with specified parent Nodes

        Parameters
        ----------
        type: str
            type of node
        parents: list of Node

        """
        if not isinstance(parents, list):
            parents = [parents]
        for i, parent in enumerate(parents):
            if isinstance(parent, str):
                parents[i] = self.nodes[parent]
        name = self.getUniqueName(type)
        node = Node(self, type, name, parents)
        node.addToScene(self.scene)

        node.button.clicked.connect(lambda: self.nodeClicked.emit(node))
        node.rightClicked.connect(lambda: self.openMenu(node))

        # resize widget in order to update widget minimum height
        node.button.clicked.connect(lambda: node.resize(node.width(), node.height()+1))

        if len(parents) == 0:
            x, y = self._mouse_position.x(), self._mouse_position.y()
            node.moveBy(x, y)
        else:
            child_pos = None
            parent_pos = None
            for i, parent in enumerate(parents):
                self.bind(parent, node)
                if len(parent.childs) > 0:
                    pos = parent.childs[-1].pos()
                    if child_pos is None or pos.x() > child_pos.x():
                        child_pos = pos
                pos = parent.pos()
                if parent_pos is None or pos.x() > parent_pos.x():
                    parent_pos = pos
                parent.childs.append(node)

            if child_pos is None or parent_pos.x() >= child_pos.x():
                node.moveBy(parent_pos.x()+300, parent_pos.y())
            else:
                node.moveBy(child_pos.x(), child_pos.y()+400)

        self.nodes[name] = node
        self.settings[name] = {'type': type, 'parents': [p.name for p in parents]}
        return node
