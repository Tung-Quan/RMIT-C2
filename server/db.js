import { readFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import pg from "pg";

export function postgresDatabase(connectionString) {
  if (!connectionString)
    throw new Error(
      "DATABASE_URL is required. Copy .env.example and configure PostgreSQL.",
    );
  const pool = new pg.Pool({ connectionString });
  return {
    query: (text, values) => pool.query(text, values),
    async transaction(run) {
      const client = await pool.connect();
      try {
        await client.query("BEGIN");
        const result = await run(client);
        await client.query("COMMIT");
        return result;
      } catch (error) {
        await client.query("ROLLBACK");
        throw error;
      } finally {
        client.release();
      }
    },
    close: () => pool.end(),
  };
}

export async function initializeDatabase(db) {
  const sql = await readFile(
    new URL("../db/migrations/001_initial.sql", import.meta.url),
    "utf8",
  );
  await db.query(sql);
  await db.transaction(async (tx) => {
    await tx.query("SELECT id FROM app_lock WHERE id=1 FOR UPDATE");
    if ((await tx.query("SELECT id FROM courses LIMIT 1")).rows.length) return;
    const seed = JSON.parse(
      await readFile(new URL("../src/seed.json", import.meta.url), "utf8"),
    );
    const staff = [
      {
        id: "registrar-1",
        name: "Taylor Reed",
        title: "Registrar",
        roles: ["registrar"],
      },
      {
        id: "approver-1",
        name: "Dr. Amara Okafor",
        title: "Head of School",
        roles: ["approver"],
      },
      {
        id: "approver-2",
        name: "Sam Williams",
        title: "Academic Advisor",
        roles: ["approver"],
      },
      {
        id: "approver-3",
        name: "Alex Morgan",
        title: "Student Representative",
        roles: ["approver"],
      },
      {
        id: "approver-4",
        name: "Robin Ellis",
        title: "Reserve Approver",
        roles: ["approver"],
      },
    ];
    for (const person of [...seed.students, ...staff]) {
      await tx.query(
        "INSERT INTO people(id,name,title,roles) VALUES($1,$2,$3,$4)",
        [
          person.id,
          person.name,
          person.title || "Student",
          JSON.stringify(person.roles || ["student"]),
        ],
      );
    }
    for (const person of staff.filter((p) =>
      ["approver-1", "approver-2", "approver-3"].includes(p.id),
    )) {
      await tx.query("INSERT INTO panel_members(person_id) VALUES($1)", [
        person.id,
      ]);
    }
    for (const course of seed.courses) {
      await tx.query(
        "INSERT INTO courses(id,code,name,capacity) VALUES($1,$2,$3,$4)",
        [course.id, course.code, course.name, course.capacity],
      );
      // Seed fixtures also obey FIFO: existing queued students fill any vacant seats first.
      const enrolled = [...course.enrolled];
      const waiting = [...course.waitlist];
      while (enrolled.length < course.capacity && waiting.length)
        enrolled.push(waiting.shift());
      for (const [status, ids] of [
        ["enrolled", enrolled],
        ["waiting", waiting],
      ]) {
        for (const id of ids)
          await tx.query(
            "INSERT INTO memberships(course_id,person_id,status) VALUES($1,$2,$3)",
            [course.id, id, status],
          );
      }
    }
  });
}

export async function linkIdentity(db, { issuer, subject, personId }) {
  if (!issuer || !subject || !personId)
    throw new Error("issuer, subject and personId are required");
  return db.transaction(async (tx) => {
    await tx.query("SELECT id FROM app_lock WHERE id=1 FOR UPDATE");
    const person = (
      await tx.query("SELECT * FROM people WHERE id=$1", [personId])
    ).rows[0];
    if (!person) throw new Error("Unknown person ID");
    // Never silently rebind an account or displace another identity.
    await tx.query(
      "INSERT INTO identities(issuer,subject,person_id) VALUES($1,$2,$3) ON CONFLICT (issuer,subject) DO NOTHING",
      [issuer, subject, personId],
    );
    const linked = (
      await tx.query(
        "SELECT person_id FROM identities WHERE issuer=$1 AND subject=$2",
        [issuer, subject],
      )
    ).rows[0];
    if (linked?.person_id !== personId)
      throw new Error("That identity is already linked to another person");
    return person;
  });
}

export const newId = () => randomUUID();
