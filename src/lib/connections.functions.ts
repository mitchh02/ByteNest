import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";

const name = z.string().trim().min(1).max(39).regex(/^[A-Za-z0-9-]+$/, "Invalid GitHub name");

export const searchConnection = createServerFn({ method: "POST" })
  .inputValidator((d) => z.object({ start: name, target: name, kind: z.enum(["user", "org"]) }).parse(d))
  .handler(async ({ data }) => {
    const { findPath } = await import("./github.server");
    try {
      return await findPath(data.start, data.target, data.kind);
    } catch (e) {
      return { found: false as const, calls: 0, explored: 0, message: (e as Error).message };
    }
  });
