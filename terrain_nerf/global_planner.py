"""Global planners

"""

import numpy as np

from terrain_nerf.astar import AStar


class GlobalPlanner(AStar):

    def __init__(self, costmap, feat_map, goal, goal_tolerance=30):
        """
        Parameters
        ----------
        costmap : CostMap
        
        """
        self.feat_map = feat_map
        self.costmap = costmap
        self.width = self.costmap.mat.shape[0]
        self.height = self.costmap.mat.shape[1]

        self.path = None
        self.goal_px = tuple(goal)     # goal in pixel coordinates
        self.goal_tolerance = goal_tolerance

    def neighbors(self, node):
        x, y = node
        return [(nx, ny) for nx, ny in [(x+1, y), (x-1, y), (x, y+1), (x, y-1)] 
                if 0 <= nx < self.width and 0 <= ny < self.height]

    def distance_between(self, node1, node2):
        return 5 * self.costmap.mat[node2]
    
    def heuristic_cost_estimate(self, node1, node2):
        """Straight line distance"""
        return np.linalg.norm(np.array(node1) - np.array(node2))
    

    def plan(self, start, goal):
        """Find a path from start to goal
        
        Start and goal are in image coordinates
        
        """
        path = list(self.astar(start, goal))
        dt = np.dtype('int32','int32')
        path = np.array(path, dtype=dt)
        return path
    

    def replan(self, cur_pose):
        """Replan"""
        x, y = self.feat_map.global_to_img(cur_pose[0], cur_pose[1])
        path = self.plan((x, y), self.goal_px)
        num_waypts = int(len(path) / 30)
        path = path[np.linspace(0, len(path)-1, num_waypts, dtype=int)]
        path_x, path_y = self.feat_map.img_to_global(path[:,0], path[:,1])
        path = np.vstack((path_x, path_y)).T
        self.path = path
        return path
    

    def plot(self, ax):
        """Plot costmap and path"""
        xmin, xmax, ymin, ymax = self.feat_map.bounds
        im = ax.imshow(self.costmap.mat, cmap='viridis', extent=[xmin, xmax, ymax, ymin])
        if self.path is not None:
            ax.plot(self.path[:,0], self.path[:,1], 'r')
            ax.scatter(self.path[:,0], self.path[:,1], c='r', s=10, marker='*')
        return im

    
    def update_costmap(self, cost_vals):
        """
        Parameters
        ----------
        pose : np.array (3,)
            [x, y, theta]
        """

        local_cost_mat = np.zeros_like(self.costmap.mat)
        for x, y, c in cost_vals:
            i, j = self.feat_map.global_to_img(x, y)
            local_cost_mat[i, j] = c

        # For each cluster 
        for k in range(self.costmap.num_clusters):
            cluster_mask = self.costmap.clusters == k
            mask = cluster_mask * local_cost_mat
            if np.sum(mask) == 0:
                continue
            avg_cost = np.mean(mask[mask > 0])
            self.costmap.vals[k] = avg_cost
            self.costmap.mat[cluster_mask] = avg_cost
    

    def update(self, cur_pose):
        """Check if goal has been reached, if so, get next waypoint

        """
        pass
