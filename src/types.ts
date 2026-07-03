export const PORT_COLORS = ["#C4847A", "#4ADE80", "#F87171", "#60A5FA", "#C084FC", "#E8EBF0"] as const

export type PortColor = (typeof PORT_COLORS)[number]

export type PortSide = "left" | "right"

export interface Port {
  id: string
  side: PortSide
  color: PortColor
  label: string
}

export type Block =
  | { id: string; type: "text"; value: string }
  | { id: string; type: "number"; value: string; label: string }
  | { id: string; type: "table"; data: string[][] }
  | { id: string; type: "image"; src: string | null }

export interface TimelineStage {
  id: string
  title: string
  tags: string[]
}

export type Node =
  | {
      id: string
      x: number
      y: number
      w: number
      title: string
      ports: Port[]
      tags: string[]
      type: "card"
      blocks: Block[]
    }
  | {
      id: string
      x: number
      y: number
      w: number
      title: string
      ports: Port[]
      tags: string[]
      type: "timeline"
      stages: TimelineStage[]
    }

export interface PortRef {
  nodeId: string
  portId: string
}

// La API expone este shape anidado (from/to con nodeId y portId), pero en la base de datos
// se guarda como columnas planas (from_node, from_port, to_node, to_port). La traducción entre
// ambas formas ocurre en el backend, en main.py, función _edge_to_schema. Este archivo no
// modela el shape plano porque el frontend nunca lo recibe ni lo envía directamente.
export interface Edge {
  id: string
  from: PortRef
  to: PortRef
  curved: boolean
  label: string
}
