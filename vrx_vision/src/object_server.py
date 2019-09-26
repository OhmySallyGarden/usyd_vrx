#!/usr/bin/env python
import rospy
import tf
import scipy.cluster.hierarchy as hcluster
import numpy
import math
from nav_msgs.srv import GetMap
from nav_msgs.msg import OccupancyGrid
from vrx_msgs.msg import ObjectArray, Object
from geometry_msgs.msg import Pose, Vector3, Quaternion
from cv_bridge import CvBridge, CvBridgeError
from sensor_msgs.msg import Image
import cv2
from threading import Thread


THRESHOLD = rospy.get_param('threshold', 80); #Min value of a cell before it is counted
DIST_THRESH = rospy.get_param('distance_threshold',3); #Distance between clusters before it is condidered seperate
EXPIRY_TIME = rospy.get_param('expiry_time', 3) #Time to before cleaning up missing objects
MARGIN_X = 200
MARGIN_Y = 150

if __name__ == "__main__":
    rospy.init_node("object_server")
    tf_broadcaster = tf.TransformBroadcaster()
    tf_listener = tf.TransformListener()


class Obstacle():
    """Obstacle Class containing information and functions for different detected Obstacles"""
    def __init__(self,object_server,frame_id,cameras):
        self.x = 0
        self.y = 0
        self.time = rospy.Time.now()
        self.rot = tf.transformations.quaternion_from_euler(0,0,0)
        self.object = Object()
        self.points = None
        self.radius = None
        #self.image_server = image_server
        self.best_guess_conf = 0
        self.object_server = object_server
        self.parent_frame = "map"
        self.object.pose.position.x = self.x
        self.object.pose.position.y = self.y
        self.object.pose.orientation.w = 1
        self.object.frame_id = frame_id;
        self.use_camera = True
        self.cameras = cameras
        self.best_image = None
        self.object.best_guess = ""



    def classify(self):
        """Here is where you request the cameras to classify the buoy"""

        #only worry about best guess and confidence atm.

        type = ""
        confidence = 0
        if self.radius < 2:
            type = "buoy"
            confidence = 0.2
        elif self.radius > 5 and self.radius < 15 :
            type = "dock"
            confidence = 0.3

        elif self.radius >= 15:
            type = "land"
            confidence = 0.2


        elif self.object.best_guess != "":
            type = self.object.best_guess

        else :
            type = "unknown"
            confidence = 0.1






        if self.use_camera == True and type=="buoy":
            for camera in self.cameras.values():
                #print("FRAME ID", self.object.frame_id,camera.frame_id)
                #if camera.name == "middle":
                try:
                    (trans, rot) = tf_listener.lookupTransform(camera.frame_id,self.object.frame_id, rospy.Time(0))
                except(tf.LookupException, tf.ConnectivityException, tf.ExtrapolationException):
                    continue

                dist=math.sqrt(math.pow(trans[0],2) + math.pow(trans[1],2))
                angle=math.atan2(trans[1],trans[0])
                if (angle < camera.fov/2 and angle > -camera.fov/2):

                    #TODO Specify this in params.
                    x_len = 1.0 #m
                    y_len = 2.0 #m
                    y_buf =0.5#m
                    x_buf =0.5#m

                    buoy_pixel_x2 = int((camera.width/2)*(1-((trans[1]-x_len/2 - x_buf)/(trans[0]*math.tan(camera.fov/2)))))
                    buoy_pixel_x1 = int((camera.width/2)*(1-((trans[1]+x_len/2 + x_buf)/(trans[0]*math.tan(camera.fov/2)))))
                    buoy_pixel_y1 = int((camera.height/2)*(1-((trans[2]+y_len+y_buf)/(trans[0]*math.tan((camera.fov*9)/(2*16))))))
                    buoy_pixel_y2 = int((camera.height/2)*(1-((trans[2]-y_buf)/(trans[0]*math.tan((camera.fov*9)/(2*16))))))
                    #print(buoy_pixel_x1,buoy_pixel_x2,buoy_pixel_y1,buoy_pixel_y2)
                    copy_img = camera.image.copy()
                    if buoy_pixel_x2 < camera.width and  buoy_pixel_x1 >0 and buoy_pixel_y1 > 0 and buoy_pixel_y2 < camera.height:
                        #crop_img = camera.image[(buoy_pixel_y1):(buoy_pixel_y2), (buoy_pixel_x1):(buoy_pixel_x2)]
                        #cv2.imshow("middle_cropped", crop_img)
                        cv2.rectangle(camera.debug_image,(buoy_pixel_x1,buoy_pixel_y1),(buoy_pixel_x2,buoy_pixel_y2),(0,0,255),1)
                        # cv2.line(copy_img,(int(buoy_pixel_x1),720),(int(buoy_pixel_x2),0),(0,0,255),1)
                        # cv2.line(copy_img,(0,buoy_pixel_y1),(1280,buoy_pixel_y2),(0,0,255),1)


        if len(self.object.confidences) == 0 or confidence > self.object.confidences[0]:
            self.object.types = [type]
            self.object.best_guess = type
            self.object.confidences = [confidence]
        else:
            pass

    def broadcast(self):
        """Broadcast the object via tf"""
        #self.object.pose.orientation=self.rot

        tf_broadcaster.sendTransform(
        (self.x,self.y,0),
        self.rot,
        rospy.Time.now(),
        self.object.frame_id,
        self.parent_frame
        )

class Camera():
    def __init__(self,name,frame_id):
        self.name = name
        self.image = None
        self.frame_id = frame_id
        self.width = 1280
        self.height = 720
        self.fov = math.radians(80) # 80 degrees


class ObjectServer():
    def __init__(self):

        self.pub = rospy.Publisher("objects", ObjectArray, queue_size="10")
        self.objects = []
        self.map = OccupancyGrid()
        self.cumulative_count=0
        self.bridge = CvBridge()
        self.cameras = {}

    def callback(self,my_map):
        """Callback when a map is called."""
        #print("Recieved Map")
        self.map = my_map


    def cameraInit(self):
        self.cameras["left"]=Camera("left","wamv/left_camera_link")
        self.cameras["middle"]=Camera("middle","wamv/middle_camera_link")
        self.cameras["right"]=Camera("right","wamv/right_camera_link")




    def cameraCallback(self,image,type):
        """Call back when image is recieved"""
        cv_image = self.bridge.imgmsg_to_cv2(image, desired_encoding="bgr8")

        self.cameras[type].image = cv_image
        self.cameras[type].debug_image = cv_image.copy()





    def process_map(self):
        #print("Processing map");
        my_map = self.map
        points_x = []
        points_y = []
        my_data = []
        info = my_map.info
        r = 0
        c = 0
        count  = 0
        #print(my_map)
        #Put map into a list of points.
        for i in my_map.data:
            if i > THRESHOLD: #If the value of the cell is > THRESHOLD append
                points_x.append(r*info.resolution)
                points_y.append(c*info.resolution)
                my_data.append((r*info.resolution,c*info.resolution))
            r = r+1
            if r == info.width:
                r = 0
                c = c +1
        if len(my_map.data)==0:
            print("Empty Map")
            return
        #Apply a distance threshold Cluster on the objects.
        #print(my_data,thresh)
        try:
            clust = hcluster.fclusterdata(my_data, DIST_THRESH, criterion="distance")
        except Exception:
            print(my_data,DIST_THRESH)
        clusters = {}
        count = 0
        for point in my_data:
            cluster_num = clust[count]
            if cluster_num not in clusters:
                clusters[cluster_num] = [point]
            else:
                clusters[cluster_num].append(point)
            count = count+1

        #Iterate through the different colusters get the average centre point distance and size
        for cluster in clusters:
            sum_x = 0
            sum_y = 0
            for point in clusters[cluster]:
                sum_x = sum_x + point[0]
                sum_y = sum_y + point[1]
            avg = (sum_x/len(clusters[cluster]), sum_y/len(clusters[cluster]))
            max_dist = 0
            for point in clusters[cluster]:
                dist = math.sqrt((avg[0] - point[0])**2 + (avg[1] - point[1])**2)
                if dist>max_dist:
                    max_dist = dist

            #Get the Distance of the x and y axis
            x = avg[0] + info.origin.position.x
            y = avg[1] + info.origin.position.y

            #If the object is close to an already found object. Consider it the same object.
            updated = False
            current_frames = []
            name = ""
            for my_obj in self.objects:
                frame_id = my_obj.object.frame_id
                current_frames.append(frame_id)
                thresh_dist = 1
                dist = math.sqrt((my_obj.x-x)**2 + (my_obj.y-y)**2)
                if (dist<thresh_dist):
                    my_obj.x = x
                    my_obj.y = y
                    my_obj.radius = max_dist
                    my_obj.points = clusters[cluster]
                    updated = True
                    name = my_obj.object.frame_id
                    my_obj.time = rospy.Time.now()
                    break
            #If it is not close to any other objects then add it as a new object.
            if updated == False:
                #print("Adding new object", self.cumulative_count)
                frame_id = str(self.cumulative_count)
                self.cumulative_count=self.cumulative_count+1
                #print(max_dist,x,y,frame_id,frame_id)
                self.add_object(clusters[cluster],max_dist,x,y,frame_id)
                #Append threw new object to the servers object list.
    def add_object(self,points,rad,x,y,frame_id):
        my_obj = Obstacle(self,frame_id,self.cameras)
        my_obj.x = x
        my_obj.y = y
        my_obj.radius = rad
        my_obj.points = points
        msg_obj = Object()
        #TODO Check if object frame number is being used.
        msg_obj.frame_id = frame_id
        my_obj.object = msg_obj
        self.objects.append(my_obj)


    def classify_objects(self):
        """Classify the objects found so far using appropiate cameras."""
        for i in self.objects:
            i.classify()
        #rospy.loginfo("Classifyed clusters")
        cv2.imshow("middle", self.cameras["middle"].debug_image)
        cv2.waitKey(1)

    def broadcast_objects(self):
        """Broadcast the objects found"""
        objectlist = ObjectArray()
        for i in self.objects:
            i.broadcast()
            if i.object.frame_id != "":
                objectlist.objects.append(i.object)
            #print(i.object)
        self.pub.publish(objectlist)

    def cleanup(self):
        """Method to clean up any objects that are old"""
        expire_time = EXPIRY_TIME
        for i in self.objects:
            time_diff = rospy.Time.now().secs - i.time.secs
            #print(i.object.frame_id, time_diff)
            if time_diff > expire_time:
                rospy.logdebug("Removing expired Object")
                self.objects.remove(i)


    def thread_func(self):
        #TODO: Add a kill function with a kill is requested.
        while not rospy.is_shutdown():
            #print("Processing")
            self.process_map()
            self.cleanup()
            rospy.sleep(0.5)

if __name__ == "__main__":

    object_server = ObjectServer()
    object_server.cameraInit()
    rate = rospy.Rate(15)
    sub = rospy.Subscriber("map",OccupancyGrid,object_server.callback)
    left = rospy.Subscriber("sensors/cameras/left_camera/image_raw",Image,object_server.cameraCallback,"left")
    middle = rospy.Subscriber("sensors/cameras/middle_camera/image_raw",Image,object_server.cameraCallback,"middle")
    left = rospy.Subscriber("sensors/cameras/right_camera/image_raw",Image,object_server.cameraCallback,"right")


    rospy.sleep(1)
    thread = Thread(target=object_server.thread_func)
    thread.start()

    count =0
    while not rospy.is_shutdown():
        # if count == 10:
        #     object_server.process_map();
        #     object_server.cleanup()
        #     count = 0
        object_server.classify_objects()
        object_server.broadcast_objects()
        count = count+1
        rate.sleep()
    thread.join()
