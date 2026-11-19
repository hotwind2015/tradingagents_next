from __future__ import annotations

from typing import Callable

from tradingagents.models.graph import GraphIR


class GraphExecutor:
    """
    批 4 简化版执行器：按 IR 顺序调用注册的节点函数。
    后续替换为 LangGraph 实现时，只需保持 execute 接口一致。
    """

    def __init__(self, ir: GraphIR):
        self.ir = ir
        self.nodes = {node.id: node for node in ir.nodes}

    def execute(self, node_fns: dict[str, Callable], initial_state: dict) -> dict:
        state = initial_state.copy()
        
        # 简单拓扑排序（此处假定无环，且由编排器保证调用顺序）
        # 真正的依赖执行留给阶段 2 的 LangGraph
        executed = set()
        while len(executed) < len(self.nodes):
            progressed = False
            for node_id, node in self.nodes.items():
                if node_id in executed:
                    continue
                
                # 检查所有指向该节点的边，其源节点是否都已执行
                incoming = [e.src for e in self.ir.edges if e.dst == node_id]
                if all(src in executed for src in incoming):
                    if node_id not in node_fns:
                        raise ValueError(f"No execution function provided for node {node_id}")
                    
                    # 执行节点
                    state = node_fns[node_id](state)
                    executed.add(node_id)
                    progressed = True
                    
            if not progressed:
                raise RuntimeError("Graph execution stalled. Cycle in graph or missing dependencies.")

        return state