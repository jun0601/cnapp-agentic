// attack-path 그래프(§5.1·§15.1) — React Flow. AWS/Azure 레인으로 크로스클라우드(2.2) 시각화.
// cross_cloud:true 엣지는 강조(애니메이션+굵게).
import { useMemo } from 'react'
import { ReactFlow, Background, Controls, MarkerType, type Node, type Edge } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { AttackPath } from '@/api/types'

const AWS_X = 60
const AZURE_X = 460
const Y_STEP = 110

const EDGE_LABEL: Record<string, string> = {
  lateral_move: '측면이동',
  credential_theft: '자격증명 탈취',
  data_exfil: '데이터 탈취',
  identity_takeover: '신원 장악',
}

export function AttackPathGraph({ path }: { path: AttackPath }) {
  const { nodes, edges } = useMemo(() => {
    // 클라우드별 레인 배치 — 등장 순서대로 y 증가
    let awsI = 0
    let azI = 0
    const rfNodes: Node[] = (path.nodes ?? []).map((n) => {
      const isAws = n.cloud === 'aws'
      const y = (isAws ? awsI++ : azI++) * Y_STEP + 20
      return {
        id: n.id,
        position: { x: isAws ? AWS_X : AZURE_X, y },
        data: { label: `${n.label}\n${n.pillar}` },
        style: {
          width: 190,
          borderRadius: 8,
          border: `2px solid ${isAws ? '#ff9900' : '#0078d4'}`,
          background: '#fff',
          fontSize: 12,
          whiteSpace: 'pre-line',
          padding: 8,
        },
      }
    })

    const rfEdges: Edge[] = (path.edges ?? []).map((e, i) => ({
      id: `e${i}`,
      source: e.from,
      target: e.to,
      label: e.label ?? EDGE_LABEL[e.type] ?? e.type,
      animated: !!e.cross_cloud,
      style: {
        stroke: e.cross_cloud ? '#dc2626' : '#64748b',
        strokeWidth: e.cross_cloud ? 3 : 1.5,
      },
      labelStyle: { fontSize: 11, fill: e.cross_cloud ? '#dc2626' : '#475569' },
      markerEnd: { type: MarkerType.ArrowClosed, color: e.cross_cloud ? '#dc2626' : '#64748b' },
    }))

    return { nodes: rfNodes, edges: rfEdges }
  }, [path])

  return (
    <div className="relative h-[520px] rounded-lg border bg-white">
      {/* 레인 라벨 */}
      <div className="pointer-events-none absolute left-4 top-2 z-10 text-xs font-bold uppercase text-aws">
        AWS · 워크로드
      </div>
      <div className="pointer-events-none absolute right-4 top-2 z-10 text-xs font-bold uppercase text-azure">
        Azure · 신원(Entra)
      </div>
      <ReactFlow nodes={nodes} edges={edges} fitView proOptions={{ hideAttribution: true }}>
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  )
}
