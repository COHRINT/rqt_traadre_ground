# Software License Agreement (BSD License)
#
# Copyright (c) 2012, Willow Garage, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of Willow Garage, Inc. nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import rospy
import tf
from tf.transformations import *

import numpy as np
import random
from math import sqrt, atan, pi, degrees, floor, atan2
from sensor_msgs.msg import *
from nav_msgs.msg import *
from cv_bridge import CvBridge, CvBridgeError

from geometry_msgs.msg import *
from traadre_msgs.msg import *
from traadre_msgs.srv import *

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

from rqt_py_common.topic_helpers import get_field_type

from QLabeledValue import *
import RobotIcon
import ObjectIcon
import QArrow

import os, csv
import rospkg
import struct
import cv2
import copy

def accepted_topic(topic):
    msg_types = [OccupancyGrid, Path, PolygonStamped, PointStamped]
    msg_type, array = get_field_type(topic)

    if not array and msg_type in msg_types:
        return True
    else:
        return False

class TraadreGroundWidget(QWidget):
    robot_state_changed = Signal()
    goal_changed = Signal()
    steer_changed = Signal(float)
        
    def __init__(self, map_topic='/map'):
        super(TraadreGroundWidget, self).__init__()

        self._layout = QVBoxLayout()
        self._h_layout = QHBoxLayout()
        self.setAcceptDrops(True)
        self.setWindowTitle('TRAADRE Ground Station')
        
        self.map = map_topic
        self._tf = tf.TransformListener()

        vNavLayout = QVBoxLayout()
 
     
        self._map_view = DEMView(map_topic, tf = self._tf, parent = self)
        #self._wordBank = HRIWordBank(parent = self)
        self._doneButton = QPushButton('Done!')
#        self._doneButton.clicked.connect(self._map_view.savePoses)
        
        #Add the word bank to the left side
        #hNavLayout.addWidget(self._wordBank)
        vNavLayout.addWidget(self._map_view)


        hNavLayout = QHBoxLayout()
               
        poseGroup = QGroupBox("Current Pose")
        poseLayout = QVBoxLayout()
        
        goalGroup = QGroupBox("Current Goal")
        goalLayout = QVBoxLayout()

        fuelGroup = QGroupBox('Current State')
        fuelLayout = QVBoxLayout()

        fuelGoalLayout = QVBoxLayout()
        
        self.poseLabels = [QLabeledValue("X"),
                QLabeledValue("Y"),
                QLabeledValue("Z"),
                QLabeledValue("Roll"),
                QLabeledValue("Pitch"),
                QLabeledValue("Yaw")]
        poseLayout.setSpacing(0)
        for label in self.poseLabels:
            poseLayout.addWidget(label)

        poseGroup.setLayout(poseLayout)
        hNavLayout.addWidget(poseGroup)

        self.goalLabels = [QLabeledValue("ID"),
                           QLabeledValue("X"),
                           QLabeledValue("Y")]
        goalLayout.setSpacing(0)
        for label in self.goalLabels:
            goalLayout.addWidget(label)

        goalGroup.setLayout(goalLayout)
        #hNavLayout.addWidget(goalGroup)


        self.fuelLabel = QLabeledValue('Fuel')
        fuelLayout.addWidget(self.fuelLabel)
        fuelGroup.setLayout(fuelLayout)
        #hNavLayout.addWidget(fuelGroup)

        fuelGoalLayout.addWidget(goalGroup)
        fuelGoalLayout.addWidget(fuelGroup)
        hNavLayout.addLayout(fuelGoalLayout)

        vNavLayout.addLayout(hNavLayout)
        self._layout.addLayout(vNavLayout)
        #self._layout.addWidget(self._doneButton)
        self.setLayout(self._layout)
        
        self.robot_state_changed.connect(self._updateState)
        self.odom_sub = rospy.Subscriber('state', RobotState, self.robot_state_cb)
        
        self.goal_changed.connect(self._updateGoal)
        self.goal_sub = rospy.Subscriber('current_goal', NamedGoal, self.goal_cb)

        #Route steer signals to both update funcs
        map(self.steer_changed.connect, [self._updateSteer, self._map_view._updateSteer])
        self.steer_pub = rospy.Publisher('steer', Steering, queue_size=10, latch=True)
        
        self.joy_sub = rospy.Subscriber('joy', Joy, self.joy_cb)
        self.goal_sub = rospy.Subscriber('current_goal', NamedGoal, self.goal_cb)
        self._goal = ('None', 0.0, 0.0)
        self.lastSteerMsg = None
        
    def _updateState(self):
        for idx, val in enumerate(self._robotState):
            self.poseLabels[idx].updateValue(val)

        self.fuelLabel.updateValue(self._robotFuel)

        #Ping unity with a steer if enabled
        '''
        if not self.lastSteerMsg is None:
            self.steer_pub.publish(self.lastSteerMsg)
        '''
        
    def _updateGoal(self):
        for idx, val in enumerate(self._goal):
            self.goalLabels[idx].updateValue(val)

    def _updateSteer(self, steer):
        steerMsg = Steering()
        steerMsg.header.stamp = rospy.Time.now()
        steerMsg.steer= steer  * 180 / math.pi

        steerMsg.id = self._goal[0]
        steerMsg.goal.x = self._goal[1]
        steerMsg.goal.y = self._goal[2]
        self.lastSteerMsg = steerMsg
        
        self.steer_pub.publish(steerMsg)
        
        #print 'Updating main widgets to ', steer
    
    
    def joy_cb(self, msg):
        #print 'Axes:', msg.axes[0], ' ', msg.axes[1]
        self.steer_changed.emit(atan2(-msg.axes[1], -msg.axes[0]))
        
    def robot_state_cb(self, msg):
        #Resolve the odometry to a screen coordinate for display

        worldX = msg.pose.position.x
        worldY = msg.pose.position.y
        worldZ = msg.pose.position.z

        
        worldRoll, worldPitch, worldYaw = euler_from_quaternion([msg.pose.orientation.x,
                                                                 msg.pose.orientation.y,
                                                                 msg.pose.orientation.z,
                                                                 msg.pose.orientation.w],'sxyz')


        #TODO: Wrap the inv rpy to [-pi, pi]
        #print 'Orientation:', msg.pose.orientation, ' RPY:', worldRoll, worldPitch, worldYaw
        
        self._robotState = [worldX, worldY, worldZ, worldRoll, worldPitch, worldYaw]
        #print 'Robot State:', self._robotState
        self._robotFuel = msg.fuel

        self.robot_state_changed.emit()
        
    def goal_cb(self, msg):
         #Resolve the odometry to a screen coordinate for display

        worldX = msg.pose.x
        worldY = msg.pose.y

        print 'Got Goal at: ' + str(worldX) + ',' + str(worldY)

        self._goal = [msg.id, worldX, worldY]
        self.goal_changed.emit()
        
    def save_settings(self, plugin_settings, instance_settings):
        self._map_view.save_settings(plugin_settings, instance_settings)

    def restore_settings(self, plugin_settings, instance_settings):
        self._map_view.restore_settings(plugin_settings, instance_settings)
        
class DEMView(QGraphicsView):
    dem_changed = Signal()
    robot_odom_changed = Signal()
    goal_changed = Signal()
    hazmap_changed = Signal()
    
    def __init__(self, dem_topic='dem',
                 tf=None, parent=None):
        super(DEMView, self).__init__()
        self._parent = parent

        self._goal_mode = True

        self.dem_changed.connect(self._update)
        self.hazmap_changed.connect(self._updateHazmap)
        self.demDownsample = 4
        self._dem_item = None
        self._goalIcon = None
        self._robotIcon = None
        
        self.setDragMode(QGraphicsView.NoDrag)

        self._addedItems = dict()
        self.w = 0
        self.h = 0

        self._colors = [(125, 0, 125), (68, 134, 252), (236, 228, 46), (102, 224, 18), (242, 156, 6), (240, 64, 10), (196, 30, 250)]
        self._scene = QGraphicsScene()

       
        self.dem_sub = rospy.Subscriber('dem', Image, self.dem_cb)
        self.odom_sub = rospy.Subscriber('state', RobotState, self.robot_odom_cb)
        
        self._robotLocation = [0,0,0,0,0,0]
        self._goalLocations = [(0,0)]
        self.arrow = None
        
        self.setScene(self._scene)

    def goal_cb(self, msg):
         #Resolve the odometry to a screen coordinate for display

        worldX = msg.pose.x
        worldY = msg.pose.y
        id = msg.id
        
        print 'Got Goal at: ' + str(worldX) + ',' + str(worldY)

        self._goalLocations[0] = [worldX, worldY]
        self._goalID = id
        self.goal_changed.emit()

    def _updateGoal(self):
        #Redraw the goal locations
        #print 'Updating goal locations'
        #If this is the first time we've seen this robot, create its icon
        if self._goalIcon is None:
            thisGoal = RobotIcon.RobotWidget(str(self._goalID), QColor(self._colors[1][0], self._colors[1][1], self._colors[1][2]))
            thisGoal.setFont(QFont("SansSerif", max(self.h / 20.0,3), QFont.Bold))
            thisGoal.setBrush(QBrush(QColor(self._colors[1][0], self._colors[1][1], self._colors[1][2])))          
            self._goalIcon = thisGoal
            self._scene.addItem(thisGoal)
            
        #Update the label's text:
        self._goalIcon.setText(str(self._goalID))
        
        #Pick up the world coordinates
        world = copy.deepcopy(self._goalLocations[0])

        iconBounds = self._goalIcon.boundingRect()

        world[0] /= self.demDownsample
        world[1] /= self.demDownsample
        
        #Adjust the world coords so that the icon is centered on the goal
        world[0] = world[0] - iconBounds.width()/2 
        world[1] = world[1] - iconBounds.height()/2 #mirror the y coord

#        world[1] = self.h - (world[1] + iconBounds.height()/2) #mirror the y coord
#        print 'Ymax:', self.h
        print 'Drawing goal ', self._goalID, ' at ', world
        self._goalIcon.setPos(QPointF(world[0], world[1]))


    def robot_odom_cb(self, msg):

        #Resolve the odometry to a screen coordinate for display from a RobotState message

        worldX = msg.pose.position.x
        worldY = msg.pose.position.y
        worldZ = msg.pose.position.z
        
        worldRoll, worldPitch, worldYaw = euler_from_quaternion([msg.pose.orientation.x,
                                                                 msg.pose.orientation.y,
                                                                 msg.pose.orientation.z,
                                                                 msg.pose.orientation.w],'sxyz')

       
        self._robotLocation = [worldX, worldY, worldZ, worldRoll, worldPitch, worldYaw]
        #print 'Robot at: ', self._robotLocations[0] 
        
        self.robot_odom_changed.emit()
        
    def _updateSteer(self, steer):
        #print 'Updating DEM view to:', steer

        #Draw the steer arrow
        if self.arrow == None:
            self.arrow = QArrow.QArrow()
            self._scene.addItem(self.arrow)

            
        iconBounds = self.arrow.boundingRect()
        world = copy.deepcopy(self._robotLocation)

        if world == [0,0,0,0,0,0]:
            print 'No coords yet received..'
            return
        
        #print 'Steering World coord:', world
        world[0] /= self.demDownsample
        world[1] /= self.demDownsample

        #Adjust the world coords so that the icon is centered on the robot, rather than top-left
        iconBounds = self.arrow.boundingRect() 
        world[0] = world[0] - iconBounds.width()/2 
        world[1] = world[1] - iconBounds.height()/2 #mirror the y coord

        #print 'Steering screen coord:', world
        self.arrow.setPos(QPointF(world[0], world[1]))
        self.arrow.setRotation(steer*180/math.pi + 90)

        #self._mirror(self.arrow)
        self.arrow.setTransformOriginPoint(QPoint(iconBounds.width()/2, iconBounds.height()/2))
        
    def _updateRobot(self):
        #Redraw the robot locations
        #print 'Updating robot locations'
        #If this is the first time we've seen this robot, create its icon
        if self._robotIcon == None:
            #thisRobot = RobotIcon.RobotWidget('R', color=QColor(self._colors[0][0], self._colors[0][1], self._colors[0][2]))
            #thisRobot.setFont(QFont("SansSerif", max(self.h / 20.0,3), QFont.Bold))
            #thisRobot.setBrush(QBrush(QColor(self._colors[0][0], self._colors[0][1], self._colors[0][2])))
            thisRobot = QArrow.QArrow(color=QColor(self._colors[0][0], self._colors[0][1], self._colors[0][2]))
            self._robotIcon = thisRobot
            self._scene.addItem(thisRobot)


            
        #Pick up the world coordinates - copy so we can change in place
        world = copy.deepcopy(self._robotLocation)
        #print 'Raw robot loc: ', world[0], world[1]
        
        iconBounds = self._robotIcon.boundingRect()

        world[0] /= self.demDownsample
        world[1] /= self.demDownsample
        
        #Adjust the world coords so that the icon is centered on the robot, rather than top-left
        world[0] = world[0] - iconBounds.width()/2 
        world[1] = world[1] - iconBounds.height()/2 #mirror the y coord

        #print 'Drawing robot at ', world[0], world[1]
        
        self._robotIcon.setPos(QPointF(world[0], world[1]))
        
        #print 'Rotating:', world[5]
        self._robotIcon.setRotation(world[5]*180/math.pi + 90)
        
        #Set the origin so that the caret rotates around its center(ish)
        self._robotIcon.setTransformOriginPoint(QPoint(iconBounds.width()/2, iconBounds.height()/2))

        #print 'Transform origin:', self._robotIcon.transformOriginPoint()
        
        #self._mirror(self._robotIcon)
        #move the Steer icon as well
        if not self.arrow is None:
            iconBounds = self.arrow.boundingRect()
            steer_world = world
            #steer_world[0] = world[0] - iconBounds.width()/2 
            #steer_world[1] = world[1] - iconBounds.height()/2 #mirror the y coord

            self.arrow.setPos(QPointF(steer_world[0], steer_world[1]))
            

                          
    def add_dragdrop(self, item):
        # Add drag and drop functionality to all the items in the view
        def c(x, e):
            self.dragEnterEvent(e)
        def d(x, e):
            self.dropEvent(e)
        item.setAcceptDrops(True)
        item.dragEnterEvent = c
        item.dropEvent = d

    def dragEnterEvent(self, e):
        print 'map enter event'

    def dropEvent(self, e):
        print 'Nav drop event'
            
    def mousePressEvent(self,e):
        return
    
    def hazmap_cb(self, msg):
        #Unlike the dem, the hazmap is pretty standard - gray8 image
        self.hazmap = CvBridge().imgmsg_to_cv2(msg, desired_encoding="passthrough")

        self.hazmapImage = QImage(self.hazmap, msg.width, msg.height, QImage.Format_Grayscale8)
        self.hazmap_changed.emit()

    def _updateHazmap(self):
        print 'Rendering hazmap'

        hazTrans = QImage(self.hazmapImage.width(), self.hazmapImage.height(), QImage.Format_ARGB32)
        #hazTrans.fill(Qt.transparent)

        for row in range(0, self.hazmapImage.height()):
            for col in range(0, self.hazmapImage.width()):
                #Change the colormap to be clear for clear areas, red translucent for obstacles

                pixColor = self.hazmap[row,col]

                if pixColor == 0:
                       #hazTrans.setPixelColor(col, row, QColor(255, 0, 0, 32))
                    hazTrans.setPixel(col,row,0xffff0000)
                else:
                       #hazTrans.setPixelColor(col, row, QColor(0, 0, 0, 0))
                    hazTrans.setPixel(col,row,0xdddddddd)


        self.hazmapItem = self._scene.addPixmap(QPixmap.fromImage(hazTrans)) #.scaled(self.w*100,self.h*100))
        self.hazmapItem.setPos(QPointF(0, 0))
        trans = QTransform()
        #print 'Translating by:', bounds.width()
        
        trans.scale(self.w/hazTrans.width(),self.h/hazTrans.height())
        #trans.translate(0, -bounds.height())
        self.hazmapItem.setTransform(trans)
        
        # Everything must be mirrored
        #self._mirror(self.hazmapItem)
        
    def dem_cb(self, msg):
        #self.resolution = msg.info.resolution
        self.w = msg.width
        self.h = msg.height

        print 'Got DEM encoded as:', msg.encoding
        print 'message length:', len(msg.data), 'type:', type(msg.data)
        print 'width:', msg.width
        print 'height:', msg.height
        
        a = np.array(struct.unpack('<%dd' % (msg.width*msg.height), msg.data), dtype=np.float64, copy=False, order='C')

   
        rawDEM = a.reshape((self.h, self.w))
        rawDEM = cv2.resize(rawDEM, (self.h//self.demDownsample, self.w//self.demDownsample), interpolation = cv2.INTER_LINEAR)
        self.h = rawDEM.shape[0]
        self.w = rawDEM.shape[1]
        
        '''
        if self.w % 4:
            e = np.zeros((self.h, 4 - self.w % 4), dtype=rawDEM.dtype, order='C')
            rawDEM = np.append(rawDEM, e, axis=1)
            self.h = rawDEM.shape[0]
            self.w = rawDEM.shape[1]
        ''' 

        #Scale to a 8-bit grayscale image:
        self.grayDEM = np.zeros(rawDEM.shape, dtype=np.uint8)
        minZ = np.min(np.min(rawDEM))
        maxZ = np.max(np.max(rawDEM))
        dynRange = maxZ - minZ

        print 'Max Z:', maxZ
        print 'Min Z:', minZ
        
        for i in range(0, self.h):
            for j in range(0, self.w):
                self.grayDEM[i][j] = (rawDEM[i][j] - minZ) * 255/dynRange

        #use OpenCV2 to interpolate the dem into something reasonably sized
        print 'Grayscale conversion complete'

        #Needs to be a class variable so that at QImage built on top of this numpy array has
        #a valid underlying buffer - local ars
        #self.resizedDEM = cv2.resize(self.grayDEM, (500,500), interpolation = cv2.INTER_LINEAR)

        print 'Image resize complete'
        
        self.h = self.grayDEM.shape[0]
        self.w = self.grayDEM.shape[1]
        image = QImage(self.grayDEM.reshape((self.h*self.w)), self.w, self.h, QImage.Format_Grayscale8)

        #        for i in reversed(range(101)):
        #            image.setColor(100 - i, qRgb(i* 2.55, i * 2.55, i * 2.55))
        #        image.setColor(101, qRgb(255, 0, 0))  # not used indices
        #        image.setColor(255, qRgb(200, 200, 200))  # color for unknown value -1

        self._dem = image       
        self.dem_changed.emit()

    def close(self):

        if self.dem_sub:
            self.dem_sub.unregister()
        if self.goal_sub:
            self.goal_sub.unregister()
        if self.pose_sub:
            self.pose_sub.unregister()
            
        super().close()
        
    def dragMoveEvent(self, e):
        print('Scene got drag move event')
        
    def resizeEvent(self, evt=None):
        #Resize map to fill window
        scale = 1
        bounds = self._scene.sceneRect()
        if bounds:
            self._scene.setSceneRect(-50, -50, self.w*scale+100, self.h*scale+100)
            self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
            self.centerOn(self._dem_item)
            self.show()
 
    def _update(self):
        if self._dem_item:
            self._scene.removeItem(self._dem_item)

        pixmap = QPixmap.fromImage(self._dem)
        self._dem_item = self._scene.addPixmap(pixmap) #.scaled(self.w*100,self.h*100))
        self._dem_item.setPos(QPointF(0, 0))
        # Everything must be mirrored
        #self._mirror(self._dem_item)

        # Add drag and drop functionality
        self.add_dragdrop(self._dem_item)

        #Resize map to fill window
        scale = 1
        self.setSceneRect(-50, -50, self.w*scale+100, self.h*scale+100)
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
        self.centerOn(self._dem_item)
        self.show()
        bounds = self._scene.sceneRect()
        #print 'Bounds:', bounds
        #Allow the robot position to be drawn on the DEM 
        self.robot_odom_changed.connect(self._updateRobot)
        self.goal_changed.connect(self._updateGoal)
        self.goal_sub = rospy.Subscriber('current_goal', NamedGoal, self.goal_cb)

        #Overlay the hazmap now that the dem is loaded
        self.hazmap_sub = rospy.Subscriber('hazmap', Image, self.hazmap_cb)

    def _mirror(self, item):
        #Get the width from the item's bounds...
        bounds = item.sceneBoundingRect()
        #print 'Bounds:', bounds
        #print 'item:', item

        trans = QTransform()
        #print 'Translating by:', bounds.width()
        
        trans.scale(1,-1)
        trans.translate(0, -bounds.height())
        item.setTransform(trans)

        #bounds = item.sceneBoundingRect()
        #print 'Bounds:', bounds

    def save_settings(self, plugin_settings, instance_settings):
        # TODO add any settings to be saved
        pass

    def restore_settings(self, plugin_settings, instance_settings):
        # TODO add any settings to be restored
        pass    

