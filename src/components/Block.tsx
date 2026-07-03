import { useRef } from "react";
import type { ReactNode } from "react";
import { X, Image as ImageIcon } from "lucide-react";
import type { Block as BlockT } from "../types";
import type { Theme } from "../lib/theme";
import { MiniBtn } from "./MiniBtn";

interface BlockProps {
  block: BlockT;
  T: Theme;
  update: (fn: (b: BlockT) => BlockT) => void;
  remove: () => void;
}

export function Block({ block, T, update, remove }: BlockProps) {
  const fileRef = useRef<HTMLInputElement>(null);

  const wrap = (children: ReactNode) => (
    <div className="relative group rounded-xl" style={{ background: T.field, border: `1px solid ${T.fieldBorder}` }}>
      <button
        className="absolute -top-2 -right-2 z-10 rounded-full p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
        style={{ background: T.card, border: `1px solid ${T.fieldBorder}`, color: T.sub }}
        onClick={remove} title="Quitar bloque"
      >
        <X size={11} />
      </button>
      {children}
    </div>
  );

  if (block.type === "text") {
    return wrap(
      <textarea
        value={block.value}
        placeholder="Escribí acá…"
        onChange={(e) => {
          update((b) => b.type === "text" ? { ...b, value: e.target.value } : b);
          e.target.style.height = "auto";
          e.target.style.height = e.target.scrollHeight + "px";
        }}
        ref={(el) => { if (el) { el.style.height = "auto"; el.style.height = el.scrollHeight + "px"; } }}
        className="w-full bg-transparent outline-none resize-none text-xs leading-relaxed px-3 py-2.5"
        style={{ color: T.text, minHeight: 38 }}
      />
    );
  }

  if (block.type === "number") {
    return wrap(
      <div className="px-3 py-2.5">
        <input
          value={block.value}
          onChange={(e) => update((b) => b.type === "number" ? { ...b, value: e.target.value } : b)}
          className="w-full bg-transparent outline-none text-xl font-semibold tracking-tight"
          style={{ color: T.text }}
        />
        <input
          value={block.label}
          onChange={(e) => update((b) => b.type === "number" ? { ...b, label: e.target.value } : b)}
          className="w-full bg-transparent outline-none text-[11px] mt-0.5"
          style={{ color: T.sub }}
        />
      </div>
    );
  }

  if (block.type === "table") {
    const data = block.data;
    const setCell = (r: number, c: number, v: string) => update((b) => {
      if (b.type !== "table") return b;
      const d = b.data.map((row) => [...row]); d[r][c] = v; return { ...b, data: d };
    });
    return wrap(
      <div className="p-2">
        <div className="grid gap-px rounded-lg overflow-hidden" style={{ gridTemplateColumns: `repeat(${data[0].length}, 1fr)`, background: T.fieldBorder }}>
          {data.map((row, r) => row.map((cell, c) => (
            <input
              key={`${r}-${c}`}
              value={cell}
              onChange={(e) => setCell(r, c, e.target.value)}
              className="bg-transparent outline-none text-[11px] px-2 py-1.5 min-w-0"
              style={{ background: T.field, color: r === 0 ? T.text : T.sub, fontWeight: r === 0 ? 600 : 400 }}
            />
          )))}
        </div>
        <div className="flex gap-1 mt-1.5">
          <MiniBtn T={T} onClick={() => update((b) => b.type === "table" ? { ...b, data: [...b.data, Array(b.data[0].length).fill("")] } : b)}>+ fila</MiniBtn>
          <MiniBtn T={T} onClick={() => update((b) => b.type === "table" ? { ...b, data: b.data.map((r) => [...r, ""]) } : b)}>+ col</MiniBtn>
          {data.length > 1 && <MiniBtn T={T} onClick={() => update((b) => b.type === "table" ? { ...b, data: b.data.slice(0, -1) } : b)}>− fila</MiniBtn>}
          {data[0].length > 1 && <MiniBtn T={T} onClick={() => update((b) => b.type === "table" ? { ...b, data: b.data.map((r) => r.slice(0, -1)) } : b)}>− col</MiniBtn>}
        </div>
      </div>
    );
  }

  if (block.type === "image") {
    return wrap(
      <div className="p-2">
        {block.src ? (
          <img src={block.src} alt="" className="w-full rounded-lg object-cover cursor-pointer" style={{ maxHeight: 180 }}
            onClick={() => fileRef.current?.click()} title="Clic para reemplazar" />
        ) : (
          <button
            className="w-full flex flex-col items-center gap-1.5 py-6 rounded-lg text-[11px]"
            style={{ color: T.sub, border: `1px dashed ${T.fieldBorder}` }}
            onClick={() => fileRef.current?.click()}
          >
            <ImageIcon size={18} /> Subir imagen
          </button>
        )}
        <input
          ref={fileRef} type="file" accept="image/*" className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (!f) return;
            const r = new FileReader();
            r.onload = () => {
              const result = r.result;
              if (typeof result !== "string") return;
              update((b) => b.type === "image" ? { ...b, src: result } : b);
            };
            r.readAsDataURL(f);
          }}
        />
      </div>
    );
  }
  return null;
}
