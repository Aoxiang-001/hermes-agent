import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectOption } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";

function isJsonStructuredArray(value: unknown): value is unknown[] {
  return Array.isArray(value) && value.some((item) => typeof item === "object" && item !== null);
}

function shouldRenderListAsJson(schemaKey: string, value: unknown): value is unknown[] {
  return schemaKey === "nim.instances" || isJsonStructuredArray(value);
}

function stringifyJson(value: unknown): string {
  return JSON.stringify(value ?? null, null, 2);
}

function JsonEditor({
  label,
  schema,
  schemaKey,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  schema: Record<string, unknown>;
  schemaKey: string;
  value: unknown;
  onChange: (v: unknown) => void;
  placeholder: string;
}) {
  const serialized = stringifyJson(value);
  const [draft, setDraft] = useState(serialized);

  useEffect(() => {
    setDraft(serialized);
  }, [serialized]);

  return (
    <div className="grid gap-1.5">
      <Label className="text-sm">{label}</Label>
      <FieldHint schema={schema} schemaKey={schemaKey} />
      <textarea
        className="flex min-h-[160px] w-full border border-input bg-transparent px-3 py-2 text-sm font-mono shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        value={draft}
        onChange={(e) => {
          const next = e.target.value;
          setDraft(next);
          try {
            onChange(JSON.parse(next));
          } catch {
            // Preserve in-progress JSON edits locally until the content is valid.
          }
        }}
        placeholder={placeholder}
        spellCheck={false}
      />
    </div>
  );
}

function FieldHint({ schema, schemaKey }: { schema: Record<string, unknown>; schemaKey: string }) {
  const keyPath = schemaKey.includes(".") ? schemaKey : "";
  const description = schema.description ? String(schema.description) : "";

  if (!keyPath && !description) return null;

  return (
    <div className="flex flex-col gap-0.5">
      {keyPath && <span className="text-[10px] font-mono text-muted-foreground/50">{keyPath}</span>}
      {description && <span className="text-xs text-muted-foreground/70">{description}</span>}
    </div>
  );
}

export function AutoField({
  schemaKey,
  schema,
  value,
  onChange,
}: AutoFieldProps) {
  const rawLabel = schemaKey.split(".").pop() ?? schemaKey;
  const label = rawLabel.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  if (schema.type === "boolean") {
    return (
      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-col gap-0.5">
          <Label className="text-sm">{label}</Label>
          <FieldHint schema={schema} schemaKey={schemaKey} />
        </div>
        <Switch checked={!!value} onCheckedChange={onChange} />
      </div>
    );
  }

  if (schema.type === "select") {
    const options = (schema.options as string[]) ?? [];
    return (
      <div className="grid gap-1.5">
        <Label className="text-sm">{label}</Label>
        <FieldHint schema={schema} schemaKey={schemaKey} />
        <Select value={String(value ?? "")} onValueChange={(v) => onChange(v)}>
          {options.map((opt) => (
            <SelectOption key={opt} value={opt}>
              {opt || "(none)"}
            </SelectOption>
          ))}
        </Select>
      </div>
    );
  }

  if (schema.type === "number") {
    return (
      <div className="grid gap-1.5">
        <Label className="text-sm">{label}</Label>
        <FieldHint schema={schema} schemaKey={schemaKey} />
        <Input
          type="number"
          value={value === undefined || value === null ? "" : String(value)}
          onChange={(e) => {
            const raw = e.target.value;
            if (raw === "") {
              onChange(0);
              return;
            }
            const n = Number(raw);
            if (!Number.isNaN(n)) {
              onChange(n);
            }
          }}
        />
      </div>
    );
  }

  if (schema.type === "text") {
    return (
      <div className="grid gap-1.5">
        <Label className="text-sm">{label}</Label>
        <FieldHint schema={schema} schemaKey={schemaKey} />
        <textarea
          className="flex min-h-[80px] w-full border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
    );
  }

  if (schema.type === "list") {
    if (shouldRenderListAsJson(schemaKey, value)) {
      return (
        <JsonEditor
          label={label}
          schema={schema}
          schemaKey={schemaKey}
          value={Array.isArray(value) ? value : []}
          onChange={onChange}
          placeholder="JSON array"
        />
      );
    }

    return (
      <div className="grid gap-1.5">
        <Label className="text-sm">{label}</Label>
        <FieldHint schema={schema} schemaKey={schemaKey} />
        <Input
          value={Array.isArray(value) ? value.join(", ") : String(value ?? "")}
          onChange={(e) =>
            onChange(
              e.target.value
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
            )
          }
          placeholder="comma-separated values"
        />
      </div>
    );
  }

  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    return (
      <JsonEditor
        label={label}
        schema={schema}
        schemaKey={schemaKey}
        value={value}
        onChange={onChange}
        placeholder="JSON object"
      />
    );
  }

  return (
    <div className="grid gap-1.5">
      <Label className="text-sm">{label}</Label>
      <FieldHint schema={schema} schemaKey={schemaKey} />
      <Input value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

interface AutoFieldProps {
  schemaKey: string;
  schema: Record<string, unknown>;
  value: unknown;
  onChange: (v: unknown) => void;
}
