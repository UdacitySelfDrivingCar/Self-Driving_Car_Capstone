#!/usr/bin/env python

import rospy
import math
import tf
from   geometry_msgs.msg import PoseStamped, TwistStamped
from   styx_msgs.msg     import Lane, Waypoint
from   std_msgs.msg      import Int32

import copy

LOOKAHEAD_WPS = 100
MAX_DECEL     = 4.0
STOP_BUFFER   = 2.5


class WaypointUpdater(object):

    def __init__(self):
        rospy.init_node('waypoint_updater')

        rospy.Subscriber('/current_pose',      PoseStamped, self.current_pose_cb)
        rospy.Subscriber('/base_waypoints',    Lane,        self.base_waypoints_cb)
        rospy.Subscriber('/traffic_waypoint',  Int32,       self.traffic_waypoint_cb)
        rospy.Subscriber('/obstacle_waypoint', Int32,       self.obstacle_waypoint_cb)
        rospy.Subscriber('/current_velocity',  TwistStamped,self.current_velocity_cb)

        self.current_velocity = 0.0
        self.decel = 1.0
        self.accel = 1.0
        self.traffic_waypoint = -1
        self.braking = False
        self.last_starting_point = None

        self.final_waypoints_pub = rospy.Publisher('final_waypoints', Lane, queue_size=1)

        rate = rospy.Rate(30)
        while not rospy.is_shutdown():
            self.loop()
            rate.sleep()


    def loop(self):
        if hasattr(self, 'base_waypoints') and hasattr(self, 'current_pose'):
            lane                 = Lane()
            lane.header.stamp    = rospy.Time().now()
            lane.header.frame_id = '/world'

            pose = self.current_pose
            wpts = self.base_waypoints.waypoints

            next_wp    = self.get_next_waypoint(pose, wpts)
            traffic_wp = self.traffic_waypoint

            # Get current distance from traffic light and minimum distance need to stop
            tl_dist = self.distance(pose.pose.position, wpts[traffic_wp].pose.pose.position)

            # The distance of speed lower down to zero, plus the distance of the road cross
            min_stopping_dist = self.current_velocity**2 / (2.0 * MAX_DECEL) + STOP_BUFFER

            # 1 If at any time, the red light disappeared, run the car normally
            if traffic_wp == -1:
                
                self.braking = False
                lane.waypoints = self.get_final_waypoints(wpts, next_wp, next_wp+LOOKAHEAD_WPS)
                self.final_waypoints_pub.publish(lane)
            # Froce stop attempt
            # elif tl_dist > STOP_BUFFER and self.current_velocity < 5:
            #     self.braking = True
            #     lane.waypoints = self.force_brake(wpts, next_wp, traffic_wp)

            #2 If red light is detected,the car is still in running mode and the distance is too short, dont stop
            #  To make it fancier and more related to the real, it should be accelerate
            elif not self.braking and tl_dist < min_stopping_dist:
                lane.waypoints = self.get_final_waypoints(wpts, next_wp, next_wp+LOOKAHEAD_WPS)

                self.final_waypoints_pub.publish(lane)
            #3 Make a stop process
            else:

                self.braking = True
                lane.waypoints = self.get_final_waypoints(wpts, next_wp, traffic_wp)
                self.final_waypoints_pub.publish(lane)




    def get_final_waypoints(self, waypoints, start_wp, end_wp):
        final_waypoints = []
        if end_wp < start_wp: # deal with the corner case that next traffic way point crossed the end of the track
            end_wp += len(waypoints) 
        
        for i in range(start_wp, end_wp + 1):
            wp = Waypoint()
            index = i % len(waypoints)
            wp.pose = copy.deepcopy(waypoints[index].pose)
            wp.twist = copy.deepcopy(waypoints[index].twist)

            final_waypoints.append(wp)
        

        if self.braking:
            final_waypoints = self.decelerate(final_waypoints)
        else:
            final_waypoints = self.accelerate(final_waypoints)
        return final_waypoints

    
    def accelerate(self, waypoints):
        # rospy.logwarn("Start accelerate")
        if self.current_velocity <= 0.0001:
            self.last_starting_point = self.current_pose.pose.position
        if self.last_starting_point is None:
            return waypoints
        for wp in waypoints:
            dist = self.distance(self.last_starting_point, wp.pose.pose.position)
            vel = math.sqrt(2 * self.accel * dist)
            if wp.twist.twist.linear.x > vel:
                wp.twist.twist.linear.x = vel
            else:
                break
        return waypoints


    def decelerate(self, waypoints):
        # rospy.logwarn("Start decelerate")
        last = waypoints[len(waypoints) - 1]
        last.twist.twist.linear.x = 0.0
        for wp in waypoints:
            dist = self.distance(wp.pose.pose.position, last.pose.pose.position)
            dist = max(0.0, dist - STOP_BUFFER)
            vel  = math.sqrt(2 * self.decel * dist)
            wp.twist.twist.linear.x = min(vel, wp.twist.twist.linear.x)
        return waypoints

    def distance(self, p1, p2):
        x = p1.x - p2.x
        y = p1.y - p2.y
        z = p1.z - p2.z
        return math.sqrt(x*x + y*y + z*z)


    def current_pose_cb(self, msg):
        self.current_pose = msg


    def base_waypoints_cb(self, msg):
        self.base_waypoints = msg


    def traffic_waypoint_cb(self, msg):
        self.traffic_waypoint = msg.data


    def current_velocity_cb(self, msg):
        self.current_velocity = msg.twist.linear.x


    def obstacle_waypoint_cb(self, msg):
        self.obstacle_waypoint = msg.data


    def get_closest_waypoint(self, pose, waypoints):
        closest_dist = float('inf')
        closest_wp = 0
        for i in range(len(waypoints)):
            dist = self.distance(pose.pose.position, waypoints[i].pose.pose.position)
            if dist < closest_dist:
                closest_dist = dist
                closest_wp = i

        return closest_wp



    def get_next_waypoint(self, pose, waypoints):
        closest_wp = self.get_closest_waypoint(pose, waypoints)
        closest_wp_next = (closest_wp + 1) % len(waypoints)
        wp0_x = waypoints[closest_wp].pose.pose.position.x
        wp0_y = waypoints[closest_wp].pose.pose.position.y
        wp1_x = waypoints[closest_wp_next].pose.pose.position.x
        wp1_y = waypoints[closest_wp_next].pose.pose.position.y
        x = pose.pose.position.x
        y = pose.pose.position.y
        if (y - wp0_y) * (wp1_y - wp0_y) + (x - wp0_x) * (wp1_x - wp0_x) >= 0:
            return closest_wp_next
        return closest_wp


    def get_next_waypoint_old(self, pose, waypoints):
        closest_wp = self.get_closest_waypoint(pose, waypoints)
        wp_x = waypoints[closest_wp].pose.pose.position.x
        wp_y = waypoints[closest_wp].pose.pose.position.y
        heading = math.atan2( (wp_y-pose.pose.position.y), (wp_x-pose.pose.position.x) )
        x = pose.pose.orientation.x
        y = pose.pose.orientation.y
        z = pose.pose.orientation.z
        w = pose.pose.orientation.w
        euler_angles_xyz = tf.transformations.euler_from_quaternion([x,y,z,w])
        theta = euler_angles_xyz[-1]
        angle = math.fabs(theta-heading)
        if angle > math.pi / 4.0:
            closest_wp += 1

        return closest_wp


if __name__ == '__main__':
    try:
        WaypointUpdater()
    except rospy.ROSInterruptException:
        rospy.logerr('Could not start waypoint updater node.')
