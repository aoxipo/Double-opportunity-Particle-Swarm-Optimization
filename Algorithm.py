import logging
import random
from copy import deepcopy
from datetime import datetime
from typing import List, Tuple

from Service_particle import Particle, Gbest
from config import *
from BBO_config import *
from edge_server import EdgeServer
from greedy_group import GreedyGroup
from service import Service, ServiceList
from utils import Random_Placement_Set
import numpy 
#import BBO as bbo

class Deployer(object):
    def __init__(self, all_edges: List[EdgeServer], distances: List[List[float]]):
        self.all_edge_list = all_edges
        logging.info('载入edge信息，共有{0}个edge'.format(len(all_edges)))
        self.distances = distances
        # self.placed_service_list = None

        # =========可变参数==============
        self.service_MAX_WORKLOAD = 0
        self.SERVICE_COVERAGE = 0
        self.MAX_TOTAL_PRICE = 0  # 200
        self.MAX_WORKOLAD_BALANCE = 0  # 25000000
        self.base_station_num=len(all_edges);
        # =========对象参数==============
        self.placed_service_list = ServiceList()
        self.result = {'price': 0, 'delay': 0, 'workload_balance': 0}

    def set_parameter(self, max_workload=srv_max_load, service_coverage=srv_coverage, price=srv_price,
                      workload_balance=srv_max_balance,base_station_num=0):
        # =========可变参数==============
        self.service_MAX_WORKLOAD = max_workload
        self.SERVICE_COVERAGE = service_coverage
        self.MAX_TOTAL_PRICE = price
        self.MAX_WORKOLAD_BALANCE = workload_balance
        if(base_station_num):
            self.base_station_num=base_station_num
            self.all_edge_list=self.all_edge_list[:self.base_station_num]
            

    def service_deployer(self):
        raise NotImplementedError

    # 计算距离
    def _distance_service_edge(self, service: Service, edge_server: EdgeServer) -> float:
        """
        Calculate distance between given edge server and base station

        :param service:
        :param edge_server:
        :return: distance(km)
        """
        if service.at_edge.base_station_id:
            return self.distances[edge_server.base_station_id][service.at_edge.base_station_id]
        return 9999  # 不在拓扑中就是无穷远

    # # 平均时延
    # def objective_latency(self):
    #     """
    #     Calculate average service access delay between edges
    #     """
    #     assert self.placed_service_list
    #     total_delay = 0
    #     edge_num = 0
    #     for s in self.placed_service_list:
    #         for es in s.served_edges:
    #             delay = self._distance_edge_bs(s, es)
    #             logging.debug("base station={0}  delay={1}".format(es.id, delay))
    #             total_delay += delay
    #             edge_num += 1
    #     return total_delay / edge_num
    #
    # # 负载标准差---->负载均衡
    # def objective_workload(self):
    #     """
    #     Calculate average edge server workload
    #
    #     Max worklaod of edge server - Min workload
    #     """
    #     assert self.placed_service_list
    #     workloads = [e.workload for e in self.placed_service_list]
    #     logging.debug("standard deviation of workload" + str(workloads))
    #     res = np.std(workloads)
    #     return res
    #
    # def service_sum(self):
    #     return len(self.placed_service_list)
    #
    # def get_service_list(self):
    #     '''
    #     :return: 返回edge的list
    #     '''
    #     return self.placed_service_list

    def get_result(self):
        self.result['delay'] = self.placed_service_list.get_average_delay()
        self.result['price'] = self.placed_service_list.get_total_price(self.base_station_num)
        self.result['workload_balance'] = self.placed_service_list.get_workload_balance()
        self.result['resource_utilization'] = self.placed_service_list.get_resource_utilization(self.base_station_num) #"NA"
        self.result['spfa']=self.placed_service_list.get_average_delay_by_spfa()

    def print_result(self, result_services=[], file=None):
        # 实验结束
        print('')
        print('实验结果'.center(50, '='), file=file)
        print('实验条件：\n\t 最大负载{}，覆盖范围{}，最高价格{}，最大负载均衡{}'.format(self.service_MAX_WORKLOAD, self.SERVICE_COVERAGE,
                                                               self.MAX_TOTAL_PRICE, self.MAX_WORKOLAD_BALANCE),
              file=file)
        print('实验结果：\n\t 平均时延{}，总价格{}，负载均衡{},资源利用率{},基站数目{},平均跳转{}'.format(self.result['delay'], self.result['price'],
                                                     self.result['workload_balance'],self.result['resource_utilization'],self.base_station_num,self.result['spfa']), file=file)
        print('实验结果'.center(50, '='), file=file)
        print('\n', file=file)

        # 打印最后一次的情况
        for s in result_services:
            print(s, file=file)

    def csv_data(self):
        return [self.service_MAX_WORKLOAD, self.SERVICE_COVERAGE, self.MAX_TOTAL_PRICE, self.MAX_WORKOLAD_BALANCE, None,
                self.result['delay'], self.result['price'], self.result['workload_balance'],self.result['resource_utilization'],self.base_station_num,
                self.result['spfa']]


class TopfirstDeployer(Deployer):
    '''
    将edge按负载从大到小排列，每次从队列中弹出最大的作为service，再从剩下的里面挑符合的edge绑定到这个service。
    以第一个被放置为service的edge作为标记区分一种TopFirst放置方法，记为record_this_loop
    如果这种放置方法不满足约束，则self.record中对应record_this_loop位置置0，从而使下一次时这个edge被放置到队尾
    '''

    def __init__(self, edge_list: List[EdgeServer], distances: List[List[float]]):
        super().__init__(edge_list, distances)
        # ============================
        self.record = [1 for i in range(len(self.all_edge_list))]  # 用于给edge做标记,如果先放a无解，则a对应位置0
        # ============================

    def service_deployer(self) -> ServiceList:
        edge_num = len(self.all_edge_list)
        logging.info("\n\n{0}:Start running TOP with edge_num={1}, service_coverage={2}".format(
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            edge_num, self.SERVICE_COVERAGE))

        while_flag = True  # 用于判断是否满足约束条件，False即满足，跳出循环
        while_count = 0  # 循环次数

        while while_flag:
            if while_count % 100 == 0:
                # print('循环次数：{}'.format(while_count))
                print('[{},{},{},{}]---->不符合约束循环次数：{}'.format(self.service_MAX_WORKLOAD, self.SERVICE_COVERAGE,
                                                              self.MAX_TOTAL_PRICE, self.MAX_WORKOLAD_BALANCE,
                                                              while_count))
            while_count += 1

            # 先清空service_list
            self.placed_service_list.clear()

            # 从小到大排序，因为pop默认从末尾弹出
            # sorted_edges = sorted(self.all_edge_list, key=lambda x: x.workload)
            sorted_edges = sorted(self.all_edge_list, key=lambda x: (x.workload * self.record[x.id]))

            count_srv_id = 0  # 给service编号

            # ============================
            record_this_loop = 0
            first_record = True  # 是否是第一个被选为service的edge
            # ============================
            while sorted_edges:  # 只要非空
                selected_edge = sorted_edges.pop()  # 队首
                # ============================
                if first_record:
                    record_this_loop = selected_edge.id
                    first_record = False
                # ============================
                new_service = Service(count_srv_id, selected_edge, max_workload=self.service_MAX_WORKLOAD)
                # new_service.add_edge(selected_edge)  # 构造函数已经添加了
                count_srv_id += 1
                # 开始随机为service绑定edge
                for edge_e in sorted_edges:
                    if new_service.distance_service_edge(edge_e) < self.SERVICE_COVERAGE:
                        if new_service.add_edge(edge_e):  # 如果可以加入edge_e
                            sorted_edges.remove(edge_e)
                        else:  # 负载已经超标了
                            break
                # 将new_service加入队列
                self.placed_service_list.add_service(new_service)

            # 判定若满足约束条件，则跳出
            
            while_flag = False

            # 如果超过edge_num，说明都试过一遍了，无解，跳出
            if while_count > edge_num and while_flag:
                self.placed_service_list.clear()
                break

        # 整理出来结果
        self.get_result()

        logging.info("{0}:End running topfirst ".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

        # ============================
        # wcsv.writerows(wwss)
        # debug_f.close()
        # ============================
        self.record = [1 for i in range(len(self.all_edge_list))]  # 还原计数数列，保证下次还有效

        return self.placed_service_list


class RandomDeployer(Deployer):

    def __init__(self, edge_list: List[EdgeServer], distances: List[List[float]]):
        super().__init__(edge_list, distances)
        self.average_reslut_dict = {'delay': [], 'price': [], 'workload_balance': []}

    def get_result(self):
        fenmu1 = len(self.average_reslut_dict['delay']) - self.average_reslut_dict['delay'].count(0)
        self.result['delay'] = 0 if fenmu1 == 0 else (sum(self.average_reslut_dict['delay']) / fenmu1)

        fenmu2 = len(self.average_reslut_dict['price']) - self.average_reslut_dict['price'].count(0)
        self.result['price'] = 0 if fenmu2 == 0 else (sum(self.average_reslut_dict['price']) / fenmu2)

        fenmu3 = len(self.average_reslut_dict['workload_balance']) - self.average_reslut_dict['workload_balance'].count(0)
        self.result['workload_balance'] = 0 if fenmu3 == 0 else ( sum(self.average_reslut_dict['workload_balance']) / fenmu3)
        self.result['resource_utilization'] = self.placed_service_list.get_resource_utilization(self.base_station_num)#"NA" #
        self.result['spfa']=self.placed_service_list.get_average_delay_by_spfa()
    def service_deployer(self) -> ServiceList:
        edge_num = len(self.all_edge_list)
        logging.info("{0}:Start running Random with edge_num={1}, service_coverage={2}".format(
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            edge_num, self.SERVICE_COVERAGE))

        # 每修改一次参数，用于求平均的字典要重置
        for record_list in self.average_reslut_dict.values():
            record_list.clear()

        # ====================迭代开始=========================
        no_ans_count = 0  # 找不到解的次数
        for loop in range(cal_average_num):  # 循环10次，求平均
            while_flag = True  # True表示不符合约束条件
            while_count = 0

            # **************************************
            #    加速点，减少无解情况的求平均数次数
            # **************************************
            # 有3次无解就不再折腾了
            if self.SERVICE_COVERAGE < 15 or self.MAX_TOTAL_PRICE < 400:
                if no_ans_count == 3:
                    break
            else:
                if no_ans_count == 5:
                    break
            # **************************************

            while while_flag:  # 找到满足约束条件的解，跳出
                if while_count % 1000 == 0:
                    print('[{},{},{},{},{}]---->不符合约束循环次数：{}'.format(loop, self.service_MAX_WORKLOAD,
                                                                     self.SERVICE_COVERAGE, self.MAX_TOTAL_PRICE,
                                                                     self.MAX_WORKOLAD_BALANCE, while_count))
                while_count += 1

                # 先清空service_list
                self.placed_service_list.clear()

                # 初始化Random_Placement_Set
                unplaced_set = Random_Placement_Set(len(self.all_edge_list))
                service_id_count = 0  # service id
                while not unplaced_set.is_empty():

                    edge_id_selected = unplaced_set.pop()
                    edge_selected = self.all_edge_list[edge_id_selected]
                    new_service = Service(service_id_count, edge_selected, max_workload=self.service_MAX_WORKLOAD)
                    # new_service.add_edge(edge_selected)  # 构造函数已经添加了
                    service_id_count += 1

                    # 开始随机为service绑定edge
                    for e in unplaced_set:
                        edge_e = self.all_edge_list[e]
                        if new_service.distance_service_edge(edge_e) < self.SERVICE_COVERAGE:  # 如果在范围内
                            if new_service.add_edge(edge_e):  # 如果可以加入edge_e，负载等不超过约束条件
                                unplaced_set.remove(e)
                            else:  # 负载已经超标了
                                break

                    # 将new_service加入队列
                    self.placed_service_list.add_service(new_service)

                # 判定若满足约束条件，则跳出
                if  self.placed_service_list.get_workload_balance() <= self.MAX_WORKOLAD_BALANCE:
                    while_flag = False  # 找到解，跳出

                # 如果超过4000循环，说明找不到，跳出
                if while_count > 4000 and while_flag:
                    self.placed_service_list.clear()
                    no_ans_count += 1  # 计一次无解
                    break  # 跳出while循环

            self.average_reslut_dict['delay'].append(self.placed_service_list.get_average_delay())
            self.average_reslut_dict['price'].append(self.placed_service_list.get_total_price(self.base_station_num))
            self.average_reslut_dict['workload_balance'].append(self.placed_service_list.get_workload_balance())
        # =============================迭代结束====================================

        self.get_result()  # 算平均
        logging.info("{0}:End running Random ".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        return self.placed_service_list


class PSODeployer(Deployer):
    def __init__(self, edge_list: List[EdgeServer], distances: List[List[float]], particle_size):
        super().__init__(edge_list, distances)
        self.PARTICLE_SIZE = particle_size
        self.MAX_GENERATION = pso_max_iteration

        # =========对象参数==============
        self.particles = []
        self.g_best = None

    def set_max_gen(self, max_gen=20):
        self.MAX_GENERATION = max_gen

    def service_deployer(self) -> ServiceList:
        edge_num = len(self.all_edge_list)
        logging.info("{0}:Start running PSO with edge_num={1}, service_coverage={2}".format(
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            edge_num, self.SERVICE_COVERAGE))
        # 初始化
        
        self.particles = [
            Particle(i, self.all_edge_list, self.distances, self.service_MAX_WORKLOAD, self.SERVICE_COVERAGE,
                     self.MAX_TOTAL_PRICE, self.MAX_WORKOLAD_BALANCE) for i in range(self.PARTICLE_SIZE)]
        # 初始化particle自动初始化pbest，故可以直接初始化gbest
  
        # 更新pbest
        for p in self.particles:
            p.init_pbest()

        self.g_best = Gbest(self.particles)
        self.g_best.update()

        # 先清空
        self.placed_service_list.clear()

        # 演进操作
        # 开始演进

        # 更新粒子
        total_price_list=[]
        total_work_list=[]
        for generation in range(self.MAX_GENERATION):
            print("\r==============覆盖半径", self.SERVICE_COVERAGE, '  基站数目', self.base_station_num, "  第", generation, '/',
                  self.MAX_GENERATION, "代==================", end='', flush=True)
            for particle in self.particles:
                state_code = particle.evolution(self.g_best)

                if state_code == 1:
                    self.get_result()
                    return self.placed_service_list  # 此时list为空

                # 更新pbest
                particle.update_pbest()

            # 更新gbest
            
            self.g_best.update()
            if srv_print_log:
                print('更新gbest ---->  基站数目', edge_num, "  第", generation, '/', self.MAX_GENERATION, "代")
            if generation !=0 and generation %flag_show_number==0 :
                id_count = 0
                for s_condition in self.g_best.condition:
                    edge_id_with_service = s_condition['location']
                    service_temp = Service(id_count, self.all_edge_list[edge_id_with_service],
                                           max_workload=self.service_MAX_WORKLOAD)
                    service_temp.workload = s_condition['workload']
                    service_temp.served_edges = [self.all_edge_list[i] for i in s_condition['serving_edges']]
                    id_count+=1
                    self.placed_service_list.add_service(service_temp)
                print("第{}代 price:{},workload_balance:{}".format(generation,self.placed_service_list.get_total_price(self.base_station_num),self.placed_service_list.get_workload_balance()))
                total_work_list.append(self.placed_service_list.get_workload_balance())
                total_price_list.append(self.placed_service_list.get_total_price(self.base_station_num))
                self.placed_service_list.clear()
        # 把结果翻译成标准输出
        # final_output_services: List[Service] = []
        id_count = 0
        for s_condition in self.g_best.condition:
            edge_id_with_service = s_condition['location']
            service_temp = Service(id_count, self.all_edge_list[edge_id_with_service],
                                   max_workload=self.service_MAX_WORKLOAD)
            service_temp.workload = s_condition['workload']
            service_temp.served_edges = [self.all_edge_list[i] for i in s_condition['serving_edges']]

            self.placed_service_list.add_service(service_temp)

            id_count += 1

        logging.info("{0}:End running PSO, max_gen={1} ".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                                                self.MAX_GENERATION))
        f=open("psoPriceConvergenceCurve.txt",'a+')
        f.writelines('\nNewstart price\n')
        f.write(str(total_price_list))
        f.writelines('\nNewstart work\n')
        f.write(str(total_work_list))
        f.close()
        # 产生结果
        self.get_result()

        # 返回
        return self.placed_service_list

    # ============================= place_server  end ========================================






class BBODeployer(Deployer):

    def __init__(self, edge_list: List[EdgeServer], distances: List[List[float]], particle_size):
        super().__init__(edge_list, distances)
        self.PARTICLE_SIZE = particle_size
        self.MAX_GENERATION = bbo_max_iteration

        # =========对象参数==============
        self.particles = []
        self.g_best = None

    def set_max_gen(self, max_gen=20):
        self.MAX_GENERATION = max_gen
    def service_deployer(self) -> ServiceList:
        edge_num = len(self.all_edge_list)
        logging.info("{0}:Start running BBO with edge_num={1}, service_coverage={2}".format(
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            edge_num, self.SERVICE_COVERAGE))
        # 初始化

        self.particles = [
            Particle(i, self.all_edge_list, self.distances, self.service_MAX_WORKLOAD, self.SERVICE_COVERAGE,
                     self.MAX_TOTAL_PRICE, self.MAX_WORKOLAD_BALANCE) for i in range(self.PARTICLE_SIZE)]  #pos
        # 初始化particle自动初始化pbest，故可以直接初始化gbest
        mu=numpy.zeros(self.PARTICLE_SIZE)
        fit = numpy.zeros(self.PARTICLE_SIZE)
        EliteSolution=numpy.zeros(self.PARTICLE_SIZE)
        EliteCost=numpy.zeros(self.PARTICLE_SIZE)
        Island=[0 for i in range(self.PARTICLE_SIZE)]
        mu=numpy.zeros(self.PARTICLE_SIZE)
        lambda1=numpy.zeros(self.PARTICLE_SIZE)
        for p in self.particles:
            p.init_pbest()
        print('bb')
        Bestpos= Gbest(self.particles)
        # 更新pbest
        

        self.g_best = Gbest(self.particles)
        self.g_best.update()
        
        #    
        for i in range(self.PARTICLE_SIZE):
            mu[i] = (self.PARTICLE_SIZE + 1 - (i)) / (self.PARTICLE_SIZE + 1)
            lambda1[i] = 1 - mu[i]
        
        # 先清空
        self.placed_service_list.clear()

        # 演进操作
        # 开始演进
        for k in range(self.PARTICLE_SIZE):
            if random.random() < lambda1[k]:
                RandomNum = random.random() * sum(mu);
                Select = mu[1];
                SelectIndex = 0;
                while (RandomNum > Select) and (SelectIndex < (self.PARTICLE_SIZE-1)):
                    SelectIndex = SelectIndex + 1;
                    Select = Select + mu[SelectIndex];
                
                Island[k] = self.particles[k]
                Island[k].update_pbest();
            else:
                Island[k] = self.particles[k]
                Island[k].update_pbest();
        #执行突变
        for k in range(self.PARTICLE_SIZE):
            if (k*0.01 > random.random() and not (Island[k]== 0)):
                Island[k].Mutation();
                Island[k].update_pbest();
                
        for k in range(self.PARTICLE_SIZE):
            Island[k].checkvalue()
            Island[k].update_pbest();
        total_price_list=[]
        total_work_list=[]
        for generation in range(self.MAX_GENERATION):
            print("\r==============覆盖半径", self.SERVICE_COVERAGE, '  基站数目', self.base_station_num, "  第", generation, '/',
                  self.MAX_GENERATION, "代==================", end='', flush=True)
            for particle in self.particles:
                particle.update_pbest()
                particle.migrate(self.g_best)
                
            self.g_best.update()
            if generation % flag_show_number ==0 and generation != 0:
                id_count = 0
                for s_condition in self.g_best.condition:
                    edge_id_with_service = s_condition['location']
                    service_temp = Service(id_count, self.all_edge_list[edge_id_with_service],
                                           max_workload=self.service_MAX_WORKLOAD)
                    service_temp.workload = s_condition['workload']
                    service_temp.served_edges = [self.all_edge_list[i] for i in s_condition['serving_edges']]
                    id_count+=1
                    self.placed_service_list.add_service(service_temp)
                #print("number:",self.placed_service_list.get_service_number())
                print("第{}代 price:{},workload_balance:{}".format(generation,self.placed_service_list.get_total_price(self.base_station_num),self.placed_service_list.get_workload_balance()))
                total_price_list.append(self.placed_service_list.get_total_price(self.base_station_num))
                total_work_list.append(self.placed_service_list.get_workload_balance())
                self.placed_service_list.clear()
                
        f=open("bboPriceConvergenceCurve.txt",'a+')
        f.writelines('\nNewstart price\n')
        f.write(str(total_price_list))
        f.writelines('\nworkload\n')
        f.write(str(total_work_list))
        f.close()
        #用新习性更换原地物种
        for k in range(self.PARTICLE_SIZE):
            self.particles[k]=Island[k]
            Island[k].update_pbest();
        
        self.g_best.update()
        # 把结果翻译成标准输出
        # final_output_services: List[Service] = []
        id_count = 0
        for s_condition in self.g_best.condition:
            edge_id_with_service = s_condition['location']
            service_temp = Service(id_count, self.all_edge_list[edge_id_with_service],
                                   max_workload=self.service_MAX_WORKLOAD)
            service_temp.workload = s_condition['workload']
            service_temp.served_edges = [self.all_edge_list[i] for i in s_condition['serving_edges']]

            self.placed_service_list.add_service(service_temp)

            id_count += 1

        logging.info("{0}:End running BBO, max_gen={1} ".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                                                self.MAX_GENERATION))

        # 产生结果
        self.get_result()

        # 返回
        return self.placed_service_list
    def is_number(s):
        try:
            float(s)
            return True
        except ValueError:
            pass
     
        try:
            import unicodedata
            unicodedata.numeric(s)
            return True
        except (TypeError, ValueError):
            pass
     
        return False









class GreedyDeployer(Deployer):

    def __init__(self, edge_list: List[EdgeServer], distances: List[List[float]]):
        """
        :param edge_list: 输入的edge放置方案
        :param distances: topology矩阵，含所有基站间的距离信息
        """
        super(GreedyDeployer, self).__init__(edge_list, distances)

        # 所有未处理的edge的集合，初始化为全部
        self.global_unattached_edges = None
        # 记录当前分组情况
        self.group_list = []

    def choose_pair_edges(self) -> Tuple:
        """
        只要self.global_unattached_edges非空，返回两个最近的edge
        :return:
        """
        if len(self.global_unattached_edges) > 1:
            p_a = self.global_unattached_edges[0]
            p_b = self.__get_nearest_node(p_a, self.global_unattached_edges)
            temp_delay = self.get_delay(p_a, p_b)
        
            if temp_delay < self.SERVICE_COVERAGE and p_a.workload+p_b.workload <= self.service_MAX_WORKLOAD:  # 满足时延约束,负载约束
                return p_a, p_b
            else:
                return p_a, None  # 不满足，只返回一个
        else:
            p_a = self.global_unattached_edges[0]
            return p_a, None

    def choose_pair_groups(self):
        """
        对 self.group_list中的group对象进行配对

        :return: pairs---->由配对的tuple组成的list，如果有落单的，single非None
        """
        pairs = []
        temp_group_list = [i for i in range(len(self.group_list))]
        while len(temp_group_list) > 0:
            if len(temp_group_list) > 1:  # 可以配对
                a_num = temp_group_list.pop()
                a = self.group_list[a_num]
                protential_b = [self.group_list[i] for i in temp_group_list]
                b = self.__get_nearest_node(a, protential_b)
                temp_group_list.remove(self.group_list.index(b))
                pairs.append((a, b))
            else:  # 只剩一个
                a_num = temp_group_list.pop()
                a = self.group_list[a_num]
                pairs.append((a, None))
        return pairs

    def merge(self, a: GreedyGroup, b: GreedyGroup):
        """
        :param a:
        :param b: b非None，a b合并，b为None，直接返回a
        :return: 输出合并的结果
        """

        # =====================================
        # print('start merge {} and {}'.format(a,b))
        # =====================================

        if b:  # 若b是非空，可以操作；若为None，不存在兼并的成对a,b，不操作
            win, lose = (a, b) if a.pk_value() >= b.pk_value() else (b, a)
            flag = False
            for item in lose.this_group:
                if win.can_absorb(item):
                    flag = True
                    break

            if flag:  # True---->存在可以插入的， 否则不可以插入，不操作
                lose_items = lose.dissolve()
                win.insert(lose_items)
                self.group_list.remove(lose)  # 从group列表中删除
                # 删除lose
                del lose

    def refill(self):
        """
        在所有的配对group都merge完之后，进行本操作
        :return:
        """
        # =====================================
        # print('start refill operation with unattached item---->{}'.format(self.global_unattached_edges))
        # =====================================

        for item in self.global_unattached_edges:
            for group in self.group_list:
                if group.can_absorb(item):
                    # =====================================
                    # print('Algorithm.global_unattached_edges---->', self.global_unattached_edges)
                    # =====================================
                    group.insert(item, self.global_unattached_edges)
                    break  # 防止item被吸收后，还要继续跟其它group比较

    def __get_nearest_node(self, item, item_list):
        """
        从itemlist中选择离item最近的

        :param item: edge或group
        :param item_list: list
        :return: edge或group
        """
        temp_dict = {}

        for i in item_list:
            temp_delay = self.__get_delay(item, i)
            if i is not item:
                if temp_delay not in temp_dict.keys():
                    temp_dict[temp_delay] = [i]    # 可以优化为随机选取
                else:
                    temp_dict[temp_delay].append(i)
        min_delay = min(temp_dict.keys())
        nearest_node = random.sample(temp_dict[min_delay],1)[0]

        return nearest_node

    def __get_delay(self, a, b):
        if isinstance(a, EdgeServer) and isinstance(b, EdgeServer):
            return self.distances[a.base_station_id][b.base_station_id]
        if isinstance(a, GreedyGroup) and isinstance(b, GreedyGroup):
            return self.distances[a.core_node.base_station_id][b.core_node.base_station_id]
    def get_delay(self, a, b):
        if isinstance(a, EdgeServer) and isinstance(b, EdgeServer):
            return self.distances[a.base_station_id][b.base_station_id]
        if isinstance(a, GreedyGroup) and isinstance(b, GreedyGroup):
            return self.distances[a.core_node.base_station_id][b.core_node.base_station_id]
        return self.distances[a.base_station_id][b.base_station_id]

    def service_deployer(self) -> ServiceList:
        """
        初始化状态是init之后的一堆含有2个edge的group
        :return: 放置结果
        """
        # logging
        edge_num = len(self.all_edge_list)
        logging.info("{0}:Start running Greedy with edge_num={1}, service_coverage={2}".format(
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            edge_num, self.SERVICE_COVERAGE))

        # 初始化，先清空
        self.placed_service_list.clear()
        self.group_list.clear()
        self.global_unattached_edges = deepcopy(self.all_edge_list)

        # 构建约束字典
        dict_limitations = {
            'workload': self.service_MAX_WORKLOAD,
            'delay': self.SERVICE_COVERAGE,
            # 'total_price': self.MAX_TOTAL_PRICE,
            # 'load_balance': self.MAX_WORKOLAD_BALANCE
        }

        # 初始化配对
        # 两两配对，初始化GreedyGroups
        while self.global_unattached_edges:
            item_a, item_b = self.choose_pair_edges()
            # =====================================
            # print('[debug] init, choose_pair---->', id(item_a))
            # print('[debug] init, choose_pair---->', id(item_b))
            # =====================================
            temp_group = GreedyGroup(self.distances, self.global_unattached_edges, dict_limitations, item_a,
                                     item_b)  # 一旦编入group，GreedyGroup构造函数会自动从self.global_unattached_edges中删除item
            self.group_list.append(temp_group)

# ===============================while start===========================================
        valid_ans = False
        no_ans_count = 0
        while not valid_ans:
            while_flag_count = 0
            console_count = 0
            while while_flag_count < 20:

                # while_flag_count += 1

                # 显示算法运行过程
                print('running greedy/while flag---->{}/{}'.format(console_count, while_flag_count))
                console_count += 1

                # last_group_list = deepcopy(self.group_list)

                # group合并
                pair_groups = self.choose_pair_groups()
                for pair in pair_groups:
                    self.merge(*pair)
                self.refill()

                # 未分配的进行回填
                while_count_2 = 0
                while self.global_unattached_edges:  # 只要refill后还有没分配的，单独成堆
                    print('while_count_2---->', while_count_2)
                    while_count_2 += 1

                    item_a, item_b = self.choose_pair_edges()
                    temp_group = GreedyGroup(self.distances, self.global_unattached_edges, dict_limitations, item_a,
                                             item_b)  # 一旦编入group，GreedyGroup构造函数会自动从self.global_unattached_edges中删除item
                    self.group_list.append(temp_group)

                # # ================================出现重复退出=====================================
                # if len(last_group_list) == len(self.group_list):  # 如果group的列表不变，则计数加一。3个循环grouplist都不变，则结束
                #     print('出现相同结果')
                #     while_flag_count += 1
                # else:
                #     while_flag_count = 0
                # # ================================出现重复退出=====================================

                # 直接计数次数退出
                while_flag_count += 1

                print('当前group个数{}'.format(len(self.group_list)))

            # 将self.group_list翻译成放置结果
            id_count = 0
            for group in self.group_list:
                service_temp = Service(id_count, group.core_node, max_workload=self.service_MAX_WORKLOAD)
                service_temp.workload = group.total_workload
                service_temp.served_edges = group.this_group

                self.placed_service_list.add_service(service_temp)
                id_count += 1

            # =====================================
            # ！！！！！！！！！！！！！！！！！！！！

            # 判断负载均衡和总价格是否满足要求
            valid_ans = True
            # ！！！！！！！！！！！！！！！！！！！！
            # =====================================
# ===============================while end===========================================

        # 产生结果
        self.get_result()

        logging.info("{}:End running Greedy with[{}, {}, {}, {}] ".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), self.SERVICE_COVERAGE, self.service_MAX_WORKLOAD, self.MAX_TOTAL_PRICE, self.MAX_WORKOLAD_BALANCE))

        # 返回
        return self.placed_service_list



# class BBODeployer(Deployer):
#     def __init__(self, edge_list: List[EdgeServer], distances: List[List[float]], particle_size):
#         super().__init__(edge_list, distances)
#         # =========对象参数==============
#         self.particles=None
#         # 迭代轮数
#         self.Iterations= BBO_Iterations
#         # 物种数量
#         self.PopulationSize = PopulationSize
#         self.all_edge_list=edge_list;
#     def set_Itera(self, max_Iter=100):
#         self.Iterations = max_Iter
#     def set_Population(self,max_Pop=30):
#         self.PopulationSize=max_Pop


#     def selector(self,algo,func_details,popSize,Iter,edge_list,distances,particle_size):
#         function_name=func_details[0]
#         lb=func_details[1]
#         ub=func_details[2]
#         dim=func_details[3]
#         sorted_edges = sorted(self.all_edge_list, key=lambda x: (x.workload * self.record[x.id]))   
#         while sorted_edges:
#             x=None
#             if(algo==0):
#                 x=bbo.BBO(Iter,sorted_edges,distances,particle_size,self.MAX_WORKOLAD_BALANCE,self.MAX_TOTAL_PRICE,self.SERVICE_COVERAGE,self.service_MAX_WORKLOAD)    
#                 new_service = Service(count_srv_id, selected_edge, max_workload=self.service_MAX_WORKLOAD)
                
#                 count_srv_id += 1
#                 # 开始为service绑定BBO得到的edge
#                 if new_service.distance_service_edge(x) < self.SERVICE_COVERAGE:
#                         if new_service.add_edge(x):  # 如果可以加入edge_e
#                             sorted_edges.remove(x)
#                 # 将new_service加入队列
#                 self.placed_service_list.add_service(new_service)    
#         return self.placed_service_list

#     def F1(self,x):
#         s=numpy.sum(x**2);
#         return s

#     def getFunctionDetails(self,a):
#         # [name, lb, ub, dim]
#         param = {  0: [F1,-100,100,30],}
#         return param.get(a, "nothing")

#     def service_deployer(self) -> ServiceList:
#         edge_num = len(self.all_edge_list)
#         logging.info("{0}:Start running BBO with edge_num={1}, service_coverage={2}".format(
#             datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
#             edge_num, self.SERVICE_COVERAGE))
        
#         #选择优化器和目标函数
#         func_details=getFunctionDetails(0)
#         service_list=selector(0,func_details,self.PopulationSize,self.Iterations)
    
        
#         # 先清空
#         self.placed_service_list.clear()

#         # 把结果翻译成标准输出
#         # final_output_services: List[Service] = []
#         id_count = 0
#         for s_condition in self.service_list:
#             edge_id_with_service = s_condition['location']
#             service_temp = Service(id_count, self.all_edge_list[edge_id_with_service],
#                                    max_workload=self.service_MAX_WORKLOAD)
#             service_temp.workload = s_condition['workload']
#             service_temp.served_edges = [self.all_edge_list[i] for i in s_condition['serving_edges']]

#             self.placed_service_list.add_service(service_temp)

#             id_count += 1

#         logging.info("{0}:End running BBO, max_gen={1} ".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
#                                                                 self.MAX_GENERATION))

#         # 产生结果
#         self.get_result()

#         # 返回
#         return self.placed_service_list

#     # ============================= place_server  end ========================================