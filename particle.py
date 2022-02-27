from utils import Random_Placement_Set
import numpy as np
from edge_server import EdgeServer
from typing import List
from utils import DataUtils
import random
from config import *
from copy import deepcopy



class Particle(object):

    def __init__(self, particle_id: int, edge_list: List[EdgeServer], distances: List[List[float]],
                 service_max_workload,
                 service_coverage, price, workload_balance):

        #  自身数据
        self.id = particle_id
        self.edge_list = edge_list
        self.distances = distances
        self.row = len(edge_list)
        self.col = len(edge_list)
        self.len=len(edge_list)
        self._matrix = []
        self.V = []
        self.pbest = {}

        # ===============可变参数=========================
        self.service_MAX_WORKLOAD = service_max_workload
        self.service_coverage = service_coverage
        self.MAX_TOTAL_PRICE = price  # 200
        self.MAX_WORKOLAD_BALANCE = workload_balance  # 25000000

        # ===============粒子初始化=======================
        self.randam_init()

    def randam_init(self):
        self._matrix = [[False for i in range(self.col)] for j in range(self.row)]
        # 速度向量随机初始化
        self.V = [True if random.random() < 0.5 else False for i in range(self.row)]
        # 产生随机序列
        unplaced_set = Random_Placement_Set(self.row)
        # 只要未放置集合非空
        while not unplaced_set.is_empty():

            # 放置service
            place_edge= unplaced_set.pop()
            self._matrix[place_edge][place_edge] = True  # 先将这个标记成已经放置

            # 待绑定的edge
            candidates = {}
            candidates_total_workload = 0

            # 找出覆盖范围内的edge
            for unplaced_edge in unplaced_set:
                if self.get_edge_distance(place_edge, unplaced_edge) <= self.service_coverage:  # 在范围内就加入备选序列
                    candidates[unplaced_edge] = 0  # 初始化
                    candidates_total_workload += self.edge_list[unplaced_edge].workload  # 计算范围内的基站的总负载

        # # ===按照Q初始化=========================================================
        #     # 计算排序权重
            for k in candidates.keys():
                distance_k = self.get_edge_distance(place_edge, k)
        
        #         # 权重计算公式
                if distance_k * candidates_total_workload > 0:
                    candidates[k] = (self.service_coverage / distance_k) + (self.edge_list[k].workload / candidates_total_workload)
        
        #     # 按权重排序
            sorted_canditates = dict(sorted(candidates.items(), key=lambda d: d[1], reverse=True))
        # # ==========================================================================

            # ===不按Q初始化===========================================================
            #sorted_canditates = candidates
            # ========================================================================


            # 开始修改矩阵，给service分配edge
            edge_temp_workload = self.edge_list[place_edge].workload
            for e in sorted_canditates.keys():
                if self.edge_list[e].workload + edge_temp_workload <= self.service_MAX_WORKLOAD:
                    self._matrix[e][place_edge] = True
                    unplaced_set.remove(e)
                    edge_temp_workload += self.edge_list[e].workload
        # 初始化后自动初始化pbest

        
        self.init_pbest()

    # ================================end of __init()__========================================================

    # 计算两个edge的距离
    def get_edge_distance(self, edge1: int, edge2: int):

        # ==============DEBUG================
        # print('edge1={},\t edge2={}'.format(edge1, edge2))
        # ===================================

        edge1_bs = self.edge_list[edge1].base_station_id
        edge2_bs = self.edge_list[edge2].base_station_id

        return  self.distances[edge1_bs][edge2_bs]
        # if self.distances[edge1_bs][edge2_bs] == 0:
        #     return DataUtils.calc_distance(self.edge_list[edge1].latitude,
        #                                    self.edge_list[edge1].longitude,
        #                                    self.edge_list[edge2].latitude,
        #                                    self.edge_list[edge2].longitude)
        # else:
        #     return self.distances[edge1_bs][edge2_bs]

    # 返回 服务的总数目
    def get_service_num(self):
        count = 0
        for i in range(self.row):
            if self._matrix[i][i]:
                count += 1
        return count

    # 某一列，是service的话返回当前的负载，不是返回0
    def get_workload_of_service_i(self, i):
        if not self._matrix[i][i]:
            return 0
        else:
            temp = 0
            for line in range(self.row):
                if self._matrix[line][i]:
                    temp += self.edge_list[line].workload
            return temp

    # 查看当前放置方案(哪些edge放了service，每个service服务哪些edge，service的负载)
    def get_condition(self):
        condition = []

        # 逐列遍历
        for i in range(self.col):
            edge = self._matrix[i][i]
            service_workload_temp = 0
            edge_list_temp = []

            if edge:
                for j in range(self.row):
                    if self._matrix[j][i]:
                        service_workload_temp += self.edge_list[j].workload
                        edge_list_temp.append(j)
                dict_temp = {'location': i, 'serving_edges': edge_list_temp, 'workload': service_workload_temp}
                condition.append(dict_temp)
        return condition

    # 计算负载均衡
    def get_workload_balance(self):
        workloads = [e['workload'] for e in self.get_condition()]
        ans = np.std(workloads)
        return ans

    # 计算平均时延
    def get_average_delay(self):
        condition = self.get_condition()
        total_delay = 0
        total_num = 0
        for srv in condition:
            location = srv['location']
            serving_edges = srv['serving_edges']
            total_num += len(serving_edges)
            for se in serving_edges:
                if self.edge_list[location].base_station_id and self.edge_list[se].base_station_id:
                    total_delay += self.distances[self.edge_list[location].base_station_id][self.edge_list[se].base_station_id]
                # else:
                #     total_delay += DataUtils.calc_distance(self.edge_list[location].latitude,
                #                                            self.edge_list[location].longitude,
                #                                            self.edge_list[se].latitude, self.edge_list[se].longitude)
        return total_delay / total_num

    # 计算总价格(待定)
    def get_total_price(self):
        # print('总价格还没确定'.center(30, '*'))
        return self.get_service_num() * 10
   
    """delay"""
    def get_average_delay_by_spfa(self):
        print("using particle spfa")
        condition = self.get_condition()
        total_delay = 0
        total_num = 0

      
        for srv in condition:
            location = srv['location']
            serving_edges = srv['serving_edges']
            total_num += len(serving_edges)
            for se in serving_edges:
                if self.edge_list[location].base_station_id and self.edge_list[se].base_station_id:
                    _,path=spfa(self.edge_list[location].base_station_id)
                    total_delay +=self.spfa_get_relay_path(self.edge_list[location].base_station_id,self.edge_list[se].base_station_id,path)
                # else:
                #     total_delay += DataUtils.calc_distance(self.edge_list[location].latitude,
                #                                            self.edge_list[location].longitude,
                #                                            self.edge_list[se].latitude, self.edge_list[se].longitude)
        return total_delay / total_num
    
    def spfa_get_relay_path(self,start,end,path):
        #print(start); #起始从start开始出发
        i=end-1
        relay=1;
        while(path[i] and path[i]!=-1 and path[i]!=start):
            relay+=1;
            print("{} to {}",i,path[i])
            i=path[i]
        return relay;

        #print(num[::-1])
    def spfa_print_path_dfs(self,node,start,path):
        if(node==start):
            print(start)
        self.spfa_print_path_dfs(path[node],start,path)
        print(node)


    def spfa(self, node=0, inf=np.inf):
        """
        单源最短路径算法，
        :param s: 距离矩阵（邻接矩阵表示）其中s[i][j]代表i到j的距离
        :param node:源点
        :return:dis 表示到每个点的距离 prenode表示路径

        核心思想
        如果一个点上次没有被松弛过，那么下次就不会从这个点开始松弛。每次把被松弛过的点加入到队列中，就可以忽略掉没有被松弛过的点

        """
        a=self.distances.copy()
        n=self.col
        m=self.row
        dis = np.ones(n) * inf
        vis = np.zeros(n, dtype=np.int8)
        dis[node] = 0
        vis[node] = 1
        que = Queue()
        prenode = -np.ones(n, dtype=np.int8)  # 记录前驱节点，没有则用-1表示
        que.put(node)
        while not que.empty():
            v = que.get()
            vis[v] = 0
            for i in range(n):
                temp = dis[v] + a[v][i]
                if a[v][i] > 0 and dis[i] > temp:
                    dis[i] = temp  # 修改最短路
                    prenode[i] = v
                    if vis[i] == 0:  # 如果扩展节点i不在队列中，入队
                        que.put(i)
                        vis[i] = 1
        return dis, prenode

    """
    delay
    """

    # 获得对角线，得到速度V
    def get_diagonal(self):
        ans = [self._matrix[i][i] for i in range(self.col)]
        return ans

    # # 初始化pbest
    def init_pbest(self):

        # print('开始为particle[{}]初始化pbest,当前delay={}'.format(self.id, self.get_average_delay()))

        # pbest是none或者新的时延更小时
        # {'matrix':[[]], 'V': [], 'condition': {}, 'workload_balance': float, 'total_price': int, 'average_delay': int}
        self.pbest['matrix'] = deepcopy(self._matrix)
        self.pbest['service_state'] = self.get_diagonal()
        self.pbest['condition'] = self.get_condition()
        self.pbest['workload_balance'] = self.get_workload_balance()
        self.pbest['average_delay'] = self.get_average_delay()
        self.pbest['total_price'] = self.get_total_price()
       
       

    # 更新pbest
    def update_pbest(self):

        # print('开始为particle[{}]更新pbest, 当前delay= {}'.format(self.id, self.pbest['average_delay']))

        # pbest是none或者新的时延更小时
        # current_delay = self.get_average_delay()
        # if self.pbest['average_delay'] > current_delay:  # 优化时延
        #if self.pbest['total_price'] < self.get_total_price():   # 优化价钱
        if self.pbest['workload_balance']>self.get_workload_balance() and self.pbest['average_delay']> self.get_average_delay():
            # {'matrix':[[]], 'V': [], 'condition': {}, 'workload_balance': float, 'total_price': int, 'average_delay': int}
            self.pbest['matrix'] = deepcopy(self._matrix)
            self.pbest['service_state'] = self.get_diagonal()
            self.pbest['condition'] = self.get_condition()
            self.pbest['workload_balance'] = self.get_workload_balance()
            self.pbest['average_delay'] = self.get_average_delay()
            self.pbest['total_price'] = self.get_total_price()
        # print('更新后，delay={}'.format(self.pbest['average_delay']))

    # 检查粒子是否合法，分别按照行列检查， ！！！仅检查放置的唯一性！！！
    # 返回出错的行号
    def check_particles(self):
        wrong_lines = set([])
        # 按行遍历
        for row in range(self.row):
            count = 0
            to_delete = False
            for col in range(self.col):
                if self._matrix[row][col]:
                    count += 1
                    # 检查是否连在有效edge上
                    if not self._matrix[col][col]:
                        # count = 999
                        to_delete = True
                        break
                    if count > 1:
                        # to_delete = True
                        break
            if count != 1:  # 0个或超过1个都不行
                to_delete = True
            # 对有标记的行加入删除集合
            if to_delete:
                wrong_lines.add(row)
                # 如果要删除的是edge，则连到它的都删除
                if self._matrix[row][row]:
                    for line in range(self.row):
                        if self._matrix[line][row]:
                            wrong_lines.add(line)
        return wrong_lines

    # 删除与回填操作
    def del_and_refill(self, wrong_lines):

        # 删除操作
        for line in wrong_lines:
            self._matrix[line] = [False for i in range(self.col)]

        # 获取当前particle状态
        service_state = self.get_diagonal()

        # 回填
        for line in wrong_lines:
            this_line_is_refilled = False

            # 先找现有的edge看能否接入
            for e in range(self.row):
                if service_state[e]:
                    # 负载不超标 且 在覆盖范围内
                    if (self.get_workload_of_service_i(e) + self.edge_list[
                        line].workload < self.service_MAX_WORKLOAD) and (
                            self.get_edge_distance(e, line) < self.service_coverage):
                        self._matrix[line][e] = True
                        this_line_is_refilled = True
                        break

            # 如果没有现有的可用，就在该edge新放置一个service
            if not this_line_is_refilled:
                self._matrix[line][line] = True

    # 更新粒子
    def evolution(self, gbest):
        # particle_now = deepcopy(self._matrix)

        t1 = self.get_average_delay()
        t2 = self.pbest['average_delay']
        t3 = gbest.average_delay
        
        t_123 = 1 / (t1+10e-6) + 1 / (t2+10e-6) + 1 / (t3+10e-6)

        p1 = (1 / (t1+10e-6)) / t_123
        p2 = (1 / (t2+10e-6)) / t_123
        p3 = (1 / (t3+10e-6)) / t_123

        if srv_print_log:
            print('粒子No.{0}更新速度，p1={1}, p2={2}, p3={3}'.format(self.id, p1, p2, p3))

        # 更新速度
        for i in range(self.col):
            r = random.random()
            if r <= p1:
                continue
            elif (r > p1) and (r <= p2 + p1):
                self.V[i] = not (self.pbest['service_state'][i] == self.get_diagonal()[i])
            else:
                self.V[i] = not gbest.service_state[i] == self.get_diagonal()[i]

        # 更新matrix
        for i in range(self.col):
            if self.V[i]:
                r = random.random()
                if r < p1:
                    continue
                if (r > p1) and (r <= p2 + p1):
                    for line in range(self.row):
                        self._matrix[line][i] = self.pbest['matrix'][line][i]
                else:
                    for line in range(self.row):
                        self._matrix[line][i] = gbest.matrix[line][i]
        # 检查错误
        wrong_lines = self.check_particles()

        # 删除&回填
        self.del_and_refill(wrong_lines)



        # 确定count的上限
        if self.MAX_TOTAL_PRICE/10 + self.service_coverage < 37:
            max_count = 1000
        else:
            max_count = 5000

        # 费用约束 和  负载均衡约束
        count = 0
        while self.get_total_price() > self.MAX_TOTAL_PRICE or self.get_workload_balance() > self.MAX_WORKOLAD_BALANCE:
            # print('----> price:{}, workload_balance:{}\n'.format(self.get_total_price(), self.get_workload_balance()))
            if count % 1000 == 0:
                if srv_print_log:
                    print('粒子No.{}: [{},{},{},{}]---->不符合约束循环次数：{}'.format(self.id, self.service_MAX_WORKLOAD,
                                                                       self.service_coverage, self.MAX_TOTAL_PRICE,
                                                                       self.MAX_WORKOLAD_BALANCE, count))
            self.randam_init()
            count += 1
   
            if count == max_count:
                return 1
        if srv_print_log:
            print('重置粒子成功，重置次数:{}'.format(count).center(50, '-'))

            print('粒子No.{0}一轮更新结束，此时错误为：{1}\n'.format(self.id, self.check_particles()))
        return 0
    def Mutation(self):
        self.randam_init();
        wrong_lines = self.check_particles()
        # 删除&回填
        self.del_and_refill(wrong_lines)
    def checkvalue(self):
        wrong_lines = self.check_particles()
        # 删除&回填
        self.del_and_refill(wrong_lines)
    def migrate(self, gbest):

        # 更新matrix
        for i in range(self.col):
            if(0.5> random.random() ):
                for line in range(self.len):
                    self._matrix[line][i] = self.pbest['matrix'][line][i]
            else:
                for line in range(self.len):
                    self._matrix[line][i] = gbest.matrix[line][i]
            # 检查错误
        wrong_lines = self.check_particles()
        # 删除&回填
        self.del_and_refill(wrong_lines)
        # 确定count的上限
        if self.MAX_TOTAL_PRICE/10 + self.service_coverage < 37:
            max_count = 1000
        else:
            max_count = 5000

        # 费用约束 和  负载均衡约束
        count = 0
        while self.get_total_price() > self.MAX_TOTAL_PRICE or self.get_workload_balance() > self.MAX_WORKOLAD_BALANCE:
            # print('----> price:{}, workload_balance:{}\n'.format(self.get_total_price(), self.get_workload_balance()))
            if count % 1000 == 0:
                if srv_print_log:
                    print('粒子No.{}: [{},{},{},{}]---->不符合约束循环次数：{}'.format(self.id, self.service_MAX_WORKLOAD,
                                                                       self.service_coverage, self.MAX_TOTAL_PRICE,
                                                                       self.MAX_WORKOLAD_BALANCE, count))
            
            self.randam_init()
            count += 1
            if count == max_count or count> max_count:
                return 1
        if srv_print_log:
            print('重置粒子成功，重置次数:{}'.format(count).center(50, '-'))

            print('粒子No.{0}一轮更新结束，此时错误为：{1}\n'.format(self.id, self.check_particles()))
        return 0
class Gbest(object):
    def __init__(self, particles: List[Particle]):
        self.particles = particles

        self.matrix = None
        self.service_state = None
        self.condition = None
        self.workload_balance = 3000000
        self.total_price = 999999
        self.average_delay = 999

    def update(self):
        #temp_particle_for_sort = sorted(self.particles, key=lambda d: d.pbest['average_delay'])
        temp_particle_for_sort = sorted(self.particles, key=lambda d: d.pbest['workload_balance'])
        temp_particle_for_sort_delay = sorted(self.particles, key=lambda d: d.pbest['average_delay'])[0]
        temp_particle_for_sort_price = sorted(self.particles, key=lambda d: d.pbest['total_price'])[0]
        # particles.sort(key=lambda d: d.pbest['average_delay'])
        best_particle = temp_particle_for_sort[0]
        #print(best_particle.pbest)
        # if best_particle.pbest['average_delay'] < self.average_delay:  # 优化时延
        #if best_particle.pbest['total_price']<self.total_price:
        print("\n")
        print(best_particle.pbest['total_price'],self.total_price)
        if best_particle.pbest['workload_balance'] < self.workload_balance and best_particle.pbest['average_delay']<self.average_delay and best_particle.pbest['total_price']<self.total_price:  # 优化价格
            self.matrix = deepcopy(best_particle.pbest['matrix'])
            self.service_state = deepcopy(best_particle.pbest['service_state'])
            self.condition = deepcopy(best_particle.get_condition())
            self.workload_balance = deepcopy(best_particle.pbest['workload_balance'])
            
            self.average_delay = deepcopy(best_particle.pbest['average_delay'])
            self.total_price =deepcopy( best_particle.pbest['total_price'])
            print('change')
        # 检查时延是否一直都是在减小
        #elif best_particle.pbest['workload_balance'] > self.workload_balance:
        #    print('error: gbest become bigger:      ',self.average_delay,'---->', best_particle.pbest['average_delay'])
        #    raise ValueError('Gbest getting bigger')
        else:
            print('not best')