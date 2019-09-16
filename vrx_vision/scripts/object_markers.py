#!/usr/bin/env python

import rospy

from interactive_markers.interactive_marker_server import *
from visualization_msgs.msg import *
from vrx_msgs.msg import ObjectArray, Object


def callback(data):
    pub = rospy.Publisher("visualization_marker",Marker,queue_size = 10)
    #print(data)
    objects = data.objects
    for i in objects:

        if i.best_guess == "buoy":

            marker = Marker()
            marker.header.frame_id = i.frame_id
            marker.header.stamp = rospy.Time.now()
            marker.ns = "basic text"
            marker.id = int(i.frame_id)
            marker.type = Marker.MESH_RESOURCE
            marker.action=Marker.ADD
            marker.mesh_resource="package://vrx_bringup/test_mesh.dae"
            #marker.text = i.best_guess +" " +  i.frame_id
            marker.scale.x = 2.0
            marker.scale.y = 2.0
            marker.scale.z = 2.0
            marker.color.r = 1.0
            marker.color.g = 0.0
            marker.color.b = 0.0
            marker.color.a = 1.0
            marker.lifetime = rospy.Duration(5)
            pub.publish(marker)
if __name__ == "__main__":
    rospy.init_node("simple_marker")
    rospy.Subscriber("objects", ObjectArray, callback)
    rospy.spin()
