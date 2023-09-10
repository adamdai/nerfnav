"""Run full simulation

"""

#import airsim_data_collection.common.setup_path
import airsim
import os
import numpy as np
import time
from matplotlib import pyplot as plt
import matplotlib as mpl
from mpl_toolkits.axes_grid1 import make_axes_locatable
import cv2 as cv
from PIL import Image

from nerfnav.autonav import AutoNav
from nerfnav.airsim_utils import get_pose2D, airsim_pose_to_Rt
from nerfnav.feature_map import FeatureMap, CostMap
from nerfnav.global_planner import GlobalPlanner

## -------------------------- PARAMS ------------------------ ##
# Unreal environment (FIXME: y inverted)
# (in unreal units, 100 unreal units = 1 meter)
UNREAL_PLAYER_START = np.array([-117252.054688, -264463.03125, 25148.908203])
UNREAL_GOAL = np.array([-83250.0, -258070.0, 24860.0])

GOAL_POS = (UNREAL_GOAL - UNREAL_PLAYER_START)[:2] / 100.0
print("GOAL_POS: ", GOAL_POS)

PLAN_TIME = 2.5  # seconds
THROTTLE = 0.4
MAX_ITERS = 1e5
GOAL_TOLERANCE = 20  # meters

VISUALIZE = True
REPLAN = True
RECORD = False
DEBUG = False

# MPL text color
COLOR = 'white'
mpl.rcParams['text.color'] = COLOR
mpl.rcParams['axes.labelcolor'] = COLOR
mpl.rcParams['xtick.color'] = COLOR
mpl.rcParams['ytick.color'] = COLOR

## -------------------------- SETUP ------------------------ ##
global_img = cv.imread('../../data/airsim/images/test_scenario.png')
global_img = global_img[::2, ::2, :]  # downscale
start_px = (138, 141)
goal_px = (78, 493)

costmap_data = np.load('../../data/airsim/costmap.npz')
costmap = CostMap(costmap_data['mat'], costmap_data['cluster_labels'], costmap_data['cluster_masks'])

feat_map = FeatureMap(global_img, start_px, goal_px, UNREAL_PLAYER_START, UNREAL_GOAL)
global_planner = GlobalPlanner(costmap, feat_map, goal_px)
nav_goal = global_planner.replan(np.zeros(3))[1]
if REPLAN:
    autonav = AutoNav(nav_goal)
else:
    autonav = AutoNav(GOAL_POS)

## -------------------------- MAIN ------------------------ ##
if __name__ == "__main__":

    # Connect to client
    client = airsim.CarClient()
    client.confirmConnection()
    client.enableApiControl(True)

    car_controls = airsim.CarControls()

    path_idx = 0
    current_pose = get_pose2D(client)

    # Visualization
    if VISUALIZE:
        f, ax = plt.subplots(2, 2)
        # Set figure size
        f.set_figwidth(16)
        f.set_figheight(9)
        f.set_facecolor(0.15 * np.ones(3))
        ax[0,0].set_title("RGB Image")
        ax[0,1].set_title("Depth Image")
        im3 = global_planner.plot(ax[1,1])
        plt.ion()
        plt.show()

    input("Press Enter to start...")

    idx = 0

    # brake the car
    car_controls.brake = 1
    car_controls.throttle = 0
    client.setCarControls(car_controls)
    # wait until car is stopped
    time.sleep(1)

    # release the brake
    car_controls.brake = 0

    # start recording data
    if RECORD:
        client.startRecording()

    try:
        while idx < MAX_ITERS:
            start_time = time.time()
            current_pose = get_pose2D(client)
            print("idx = ", idx)
            print("  current_pose: ", current_pose)
            print("  nav_goal: ", nav_goal)
            if np.linalg.norm(current_pose[:2] - GOAL_POS) < GOAL_TOLERANCE:
                print("Reached goal!")
                break

            # Get depth image
            responses = client.simGetImages([airsim.ImageRequest("Depth", airsim.ImageType.DepthPlanar, pixels_as_float=True, compress=False)])
            camera_info = client.simGetCameraInfo("Depth")
            cam_pose = airsim_pose_to_Rt(camera_info.pose)
            depth_float = np.array(responses[0].image_data_float)
            depth_float = depth_float.reshape(responses[0].height, responses[0].width)
            # Get RGB image
            image = client.simGetImage("FrontCamera", airsim.ImageType.Scene)
            image = cv.imdecode(np.frombuffer(image, np.uint8), -1)

            img_time = time.time()
            if DEBUG:
                print("  img capture time: ", img_time - start_time)

            cost_vals = autonav.update_costmap(current_pose, depth_float)
            local_update_time = time.time()
            if DEBUG:
                print("  local cost update time: ", local_update_time - img_time)
            if REPLAN:
                global_planner.update_costmap(cost_vals)
                global_update_time = time.time()
                if DEBUG:
                    print("  global cost update time: ", global_update_time - local_update_time)
            path = global_planner.replan(current_pose)
            global_replan_time = time.time()
            if DEBUG:
                print("  global replan time: ", global_replan_time - global_update_time)
            if len(path) > 1:
                nav_goal = path[1]
            else:
                nav_goal = GOAL_POS
            autonav.update_goal(nav_goal)
            arc, cost, w = autonav.replan(current_pose)
            local_replan_time = time.time()
            if DEBUG:
                print("  local replan time: ", local_replan_time - global_replan_time)

            car_controls.steering = w / 1.6
            car_controls.throttle = THROTTLE
            client.setCarControls(car_controls)
            #print("steering: ", car_controls.steering, "throttle: ", car_controls.throttle)
            plan_time = time.time() - start_time
            if DEBUG:
                print("  planning time: ", plan_time)
            if plan_time < PLAN_TIME:
                time.sleep(PLAN_TIME - plan_time)
            print("--------------------------------------------------------------------------------")

            if VISUALIZE:
                #ax1.clear(); ax2.clear(); ax3.clear()
                ax[0,0].clear(); ax[0,1].clear(); ax[1,0].clear(); ax[1,1].clear()
                ax[0,0].set_title("RGB Image")
                ax[0,1].set_title("Depth Image")
                ax[0,0].imshow(image)
                # depth_image = Image.fromarray(depth_float)
                # depth_image = depth_image.convert("L")
                # ax[0,1].imshow(depth_image)
                ax[0,1].imshow(depth_float)
                im2 = autonav.plot_costmap(ax[1,0], show_arcs=True)
                ax[1,0].set_title(f"Local costmap \n Max cost = {np.max(autonav.costmap)}")
                ax[1,0].set_xlabel("y (m)")
                ax[1,0].set_ylabel("x (m)")
                im3 = global_planner.plot(ax[1,1])
                ax[1,1].set_title(f"Global costmap \n Max cost = {np.max(global_planner.costmap.mat)}")
                ax[1,1].set_xlabel("x (m)")
                ax[1,1].set_ylabel("y (m)")
                #cbar3.set_clim(vmin=0, vmax=np.max(global_planner.costmap))
                # plt.colorbar(im3, ax=ax[1], fraction=0.05, aspect=10)  # FIXME: makes a new colorbar every time
                plt.pause(autonav.arc_duration - PLAN_TIME)
            else:
                time.sleep(autonav.arc_duration - PLAN_TIME)
            idx += 1
    
    except KeyboardInterrupt:
        if RECORD:
            client.stopRecording()
        # Restore to original state
        client.reset()
        client.enableApiControl(False)

    if RECORD:
        client.stopRecording()
    # Restore to original state
    client.reset()
    client.enableApiControl(False)

    



