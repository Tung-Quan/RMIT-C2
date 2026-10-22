import { createHash } from "node:crypto";
import { assert } from "./errors.js";
import { newId } from "./db.js";

const row = async (tx, sql, args = []) => (await tx.query(sql, args)).rows[0];
export const has = (user, role) => user.roles.includes(role);
const staff = (user) => has(user, "registrar") || has(user, "approver");
const canonical = (value) =>
  JSON.stringify(
    value && typeof value === "object"
      ? Array.isArray(value)
        ? value.map((v) => JSON.parse(canonical(v)))
        : Object.fromEntries(
            Object.keys(value)
              .sort()
              .map((k) => [k, JSON.parse(canonical(value[k]))]),
          )
      : value,
  );

export async function currentUser(db, claims) {
  const person = await row(
    db,
    `SELECT p.* FROM people p JOIN identities i ON i.person_id=p.id
    WHERE i.issuer=$1 AND i.subject=$2`,
    [claims.iss, claims.sub],
  );
  assert(
    person?.active,
    403,
    "ACCOUNT_NOT_LINKED",
    "This Tide identity needs an active FairEnrol account. Ask the registrar to provision it.",
  );
  const tokenRoles = new Set([
    ...(claims.realm_access?.roles || []),
    ...(claims.resource_access?.[claims.azp]?.roles || []),
  ]);
  if (tokenRoles.has("appUser")) tokenRoles.add("student");
  const roles = person.roles.filter((role) => tokenRoles.has(role));
  assert(
    roles.length,
    403,
    "ROLE_REQUIRED",
    "Your Tide roles do not match the roles assigned to this FairEnrol account.",
  );
  return { id: person.id, name: person.name, title: person.title, roles };
}

async function audit(tx, user, kind, summary, requestId = null) {
  await tx.query(
    "INSERT INTO audit_events(actor_id,kind,summary,request_id) VALUES($1,$2,$3,$4)",
    [user.id, kind, summary, requestId],
  );
}

export async function publicExceptions(db) {
  return (
    await db.query(`SELECT id,kind,public_reason AS reason,created_at AS "createdAt"
    FROM exception_requests WHERE status='approved' ORDER BY created_at DESC LIMIT 100`)
  ).rows;
}

export async function snapshot(db, user) {
  return db.transaction(async (tx) => {
    // A consistent view of courses, approvals and panel, across multiple API instances.
    await tx.query("SELECT id FROM app_lock WHERE id=1 FOR SHARE");
    const courses = (await tx.query("SELECT * FROM courses ORDER BY code"))
      .rows;
    const memberships = (
      await tx.query("SELECT * FROM memberships ORDER BY sort_order,person_id")
    ).rows;
    const panel = (
      await tx.query(
        "SELECT p.id,p.name,p.title FROM people p JOIN panel_members pm ON pm.person_id=p.id ORDER BY p.id",
      )
    ).rows;
    const people = staff(user)
      ? (
          await tx.query(
            "SELECT id,name,title,roles FROM people WHERE active=true ORDER BY name",
          )
        ).rows
      : [];
    const requests = staff(user)
      ? (
          await tx.query(`SELECT e.*,p.name AS requester FROM exception_requests e
      JOIN people p ON p.id=e.requester_id ORDER BY e.created_at DESC LIMIT 100`)
        ).rows
      : [];
    const approvals = staff(user)
      ? (
          await tx.query(`SELECT a.request_id,p.id,p.name FROM request_approvals a
      JOIN people p ON p.id=a.approver_id ORDER BY a.created_at`)
        ).rows
      : [];
    const auditLog = (
      await tx.query(
        `SELECT id,kind,summary,created_at AS time FROM audit_events ORDER BY id DESC LIMIT 50`,
      )
    ).rows;
    return {
      user,
      panel,
      people,
      courses: courses.map((c) => {
        const entries = memberships.filter((m) => m.course_id === c.id);
        const waiting = entries.filter((m) => m.status === "waiting");
        const mine = entries.find((m) => m.person_id === user.id);
        return {
          ...c,
          enrolledCount: entries.filter((m) => m.status === "enrolled").length,
          waitingCount: waiting.length,
          myStatus: mine?.status || null,
          myPosition:
            mine?.status === "waiting"
              ? waiting.findIndex((m) => m.person_id === user.id) + 1
              : null,
          ...(staff(user)
            ? {
                roster: entries.map((m) => ({
                  personId: m.person_id,
                  status: m.status,
                })),
              }
            : {}),
        };
      }),
      requests: requests.map((r) => ({
        id: r.id,
        kind: r.kind,
        requesterId: r.requester_id,
        requester: r.requester,
        data: r.data,
        reason: r.reason,
        publicReason: r.public_reason,
        status: r.status,
        createdAt: r.created_at,
        panelSnapshot: r.panel_snapshot,
        approvals: approvals
          .filter((a) => a.request_id === r.id)
          .map(({ id, name }) => ({ id, name })),
      })),
      publicExceptions: await publicExceptions(tx),
      audit: auditLog,
    };
  });
}

export async function mutate(db, user, route, key, body, run) {
  assert(
    typeof key === "string" && /^[\w-]{8,100}$/.test(key),
    400,
    "IDEMPOTENCY_KEY_REQUIRED",
    "Provide an Idempotency-Key of 8–100 letters, numbers, underscores or hyphens.",
  );
  const fingerprint = createHash("sha256")
    .update(canonical(body))
    .digest("hex");
  return db.transaction(async (tx) => {
    // A single row lock deliberately serializes this small application's mutations, including panel changes.
    // This is database-backed, so concurrent processes share the same consistency boundary.
    await tx.query("SELECT id FROM app_lock WHERE id=1 FOR UPDATE");
    const person = await row(
      tx,
      "SELECT active,roles FROM people WHERE id=$1",
      [user.id],
    );
    assert(
      person?.active && user.roles.every((r) => person.roles.includes(r)),
      403,
      "ACCOUNT_DISABLED",
      "Account permissions changed. Sign in again.",
    );
    const previous = await row(
      tx,
      "SELECT * FROM mutation_keys WHERE person_id=$1 AND route=$2 AND key=$3",
      [user.id, route, key],
    );
    if (previous) {
      assert(
        previous.fingerprint === fingerprint,
        409,
        "IDEMPOTENCY_CONFLICT",
        "This idempotency key was used for different data.",
      );
      return previous.response;
    }
    const response = await run(tx);
    await tx.query(
      "INSERT INTO mutation_keys(person_id,route,key,fingerprint,response) VALUES($1,$2,$3,$4,$5)",
      [user.id, route, key, fingerprint, JSON.stringify(response)],
    );
    return response;
  });
}

async function courseById(tx, id) {
  const course = await row(tx, "SELECT * FROM courses WHERE id=$1", [id]);
  assert(course, 404, "COURSE_NOT_FOUND", "Course not found.");
  return course;
}

async function invalidateCourseRequests(tx, courseId, exclude = "") {
  await tx.query(
    "UPDATE exception_requests SET status='stale' WHERE status='pending' AND data->>'courseId'=$1 AND id<>$2",
    [courseId, exclude],
  );
}

async function promote(tx, course) {
  const count = Number(
    (
      await row(
        tx,
        "SELECT count(*) AS n FROM memberships WHERE course_id=$1 AND status='enrolled'",
        [course.id],
      )
    ).n,
  );
  const seats = Math.max(0, course.capacity - count);
  if (seats)
    await tx.query(
      `UPDATE memberships SET status='enrolled' WHERE course_id=$1 AND person_id IN
    (SELECT person_id FROM memberships WHERE course_id=$1 AND status='waiting' ORDER BY sort_order,person_id LIMIT $2)`,
      [course.id, seats],
    );
}

export async function enrol(tx, user, courseId, withdraw = false) {
  assert(
    has(user, "student"),
    403,
    "FORBIDDEN",
    "Only students can change their own enrolments.",
  );
  const course = await courseById(tx, courseId);
  const existing = await row(
    tx,
    "SELECT status FROM memberships WHERE course_id=$1 AND person_id=$2",
    [courseId, user.id],
  );
  if (withdraw) {
    if (!existing) return { message: "You are not enrolled or waiting." };
    await tx.query(
      "DELETE FROM memberships WHERE course_id=$1 AND person_id=$2",
      [courseId, user.id],
    );
    await promote(tx, course);
  } else {
    if (existing)
      return {
        message:
          existing.status === "enrolled"
            ? "You are already enrolled."
            : "You are already on the waitlist.",
      };
    await tx.query(
      "INSERT INTO memberships(course_id,person_id,status) VALUES($1,$2,'waiting')",
      [courseId, user.id],
    );
    await promote(tx, course);
  }
  await tx.query("UPDATE courses SET version=version+1 WHERE id=$1", [
    courseId,
  ]);
  await invalidateCourseRequests(tx, courseId);
  await audit(
    tx,
    user,
    withdraw ? "enrolment.withdrawn" : "enrolment.joined",
    `${course.code}: ${withdraw ? "a place was released; waiting students were promoted in order." : "an enrolment or FIFO waitlist entry was recorded."}`,
  );
  return {
    message: withdraw
      ? "Place released. The waitlist has been updated."
      : "Your enrolment or waitlist position is recorded.",
  };
}

export async function setCapacity(tx, user, courseId, capacity) {
  assert(
    has(user, "registrar"),
    403,
    "FORBIDDEN",
    "Registrar permission is required.",
  );
  const course = await courseById(tx, courseId);
  const count = Number(
    (
      await row(
        tx,
        "SELECT count(*) AS n FROM memberships WHERE course_id=$1 AND status='enrolled'",
        [courseId],
      )
    ).n,
  );
  assert(
    capacity >= count,
    409,
    "CAPACITY_BELOW_ENROLMENT",
    "The limit cannot be reduced below current enrolment.",
  );
  await tx.query(
    "UPDATE courses SET capacity=$2,version=version+1 WHERE id=$1",
    [courseId, capacity],
  );
  await promote(tx, { ...course, capacity });
  await invalidateCourseRequests(tx, courseId);
  await audit(
    tx,
    user,
    "capacity.changed",
    `${course.code}: capacity changed to ${capacity}; available places were offered in FIFO order.`,
  );
  return { message: "Capacity saved and waitlist promoted in order." };
}

export async function createRequest(tx, user, body) {
  assert(
    staff(user),
    403,
    "FORBIDDEN",
    "Registrar or approver permission is required.",
  );
  const { kind, reason, publicReason, ...data } = body;
  const panel = (
    await tx.query("SELECT person_id FROM panel_members ORDER BY person_id")
  ).rows.map((p) => p.person_id);
  assert(
    panel.length === 3,
    409,
    "PANEL_NOT_READY",
    "A three-person panel must be configured.",
  );
  let courseVersion = null;
  if (kind === "panel") {
    assert(
      panel.includes(data.replaceId) && !panel.includes(data.candidateId),
      400,
      "INVALID_PANEL_CHANGE",
      "Select a current member and a different eligible replacement.",
    );
    const candidate = await row(
      tx,
      "SELECT roles,active FROM people WHERE id=$1",
      [data.candidateId],
    );
    assert(
      candidate?.active && candidate.roles.includes("approver"),
      400,
      "INELIGIBLE_CANDIDATE",
      "The replacement must already be an active eligible approver.",
    );
  } else {
    const course = await courseById(tx, data.courseId);
    courseVersion = course.version;
    const student = await row(
      tx,
      "SELECT roles,active FROM people WHERE id=$1",
      [data.studentId],
    );
    assert(
      student?.active && student.roles.includes("student"),
      400,
      "INVALID_STUDENT",
      "Select an active student.",
    );
    const member = await row(
      tx,
      "SELECT status FROM memberships WHERE course_id=$1 AND person_id=$2",
      [data.courseId, data.studentId],
    );
    if (kind === "force") {
      assert(
        member?.status !== "enrolled",
        409,
        "ALREADY_ENROLLED",
        "That student is already enrolled.",
      );
      const count = Number(
        (
          await row(
            tx,
            "SELECT count(*) AS n FROM memberships WHERE course_id=$1 AND status='enrolled'",
            [course.id],
          )
        ).n,
      );
      data.resultingCapacity = Math.max(course.capacity, count + 1);
      assert(
        data.resultingCapacity <= 10000,
        409,
        "MAX_CAPACITY",
        "The approved action would exceed the supported course limit.",
      );
    } else
      assert(
        member && (kind !== "jump" || member.status === "waiting"),
        409,
        "INVALID_MEMBERSHIP",
        "The target must be enrolled or waiting; queue jumps require a waitlist entry.",
      );
  }
  const version = (
    await row(tx, "SELECT panel_version FROM app_lock WHERE id=1")
  ).panel_version;
  const id = newId();
  await tx.query(
    `INSERT INTO exception_requests(id,kind,requester_id,data,reason,public_reason,panel_snapshot,panel_version,course_version)
    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)`,
    [
      id,
      kind,
      user.id,
      JSON.stringify(data),
      reason,
      publicReason,
      JSON.stringify(panel),
      version,
      courseVersion,
    ],
  );
  await audit(
    tx,
    user,
    "exception.requested",
    `A ${kind} exception was submitted for independent review.`,
    id,
  );
  return {
    id,
    message: "Request submitted. Two independent approvals are required.",
  };
}

export async function vote(tx, user, requestId, deny = false) {
  assert(
    has(user, "approver"),
    403,
    "FORBIDDEN",
    "Approver permission is required.",
  );
  const request = await row(
    tx,
    "SELECT * FROM exception_requests WHERE id=$1",
    [requestId],
  );
  assert(request, 404, "REQUEST_NOT_FOUND", "Request not found.");
  assert(
    request.status !== "stale",
    409,
    "STALE_REQUEST",
    "The course or panel changed. Submit a new request.",
  );
  assert(
    request.status === "pending",
    409,
    "REQUEST_CLOSED",
    "This request is no longer pending.",
  );
  const version = (
    await row(tx, "SELECT panel_version FROM app_lock WHERE id=1")
  ).panel_version;
  const onPanel = await row(
    tx,
    "SELECT person_id FROM panel_members WHERE person_id=$1",
    [user.id],
  );
  assert(
    onPanel && request.panel_snapshot.includes(user.id),
    403,
    "NOT_ON_PANEL",
    "Only the panel recorded on this request may review it.",
  );
  assert(
    request.requester_id !== user.id,
    403,
    "SELF_APPROVAL",
    "You cannot review your own request.",
  );
  assert(
    version === request.panel_version,
    409,
    "STALE_REQUEST",
    "Panel authority changed. Submit a new request.",
  );
  let course;
  if (request.kind !== "panel") {
    course = await courseById(tx, request.data.courseId);
    assert(
      course.version === request.course_version,
      409,
      "STALE_REQUEST",
      "The course changed since this request was submitted. Submit a new request.",
    );
    const target = await row(
      tx,
      "SELECT roles,active FROM people WHERE id=$1",
      [request.data.studentId],
    );
    assert(
      target?.active && target.roles.includes("student"),
      409,
      "INVALID_STUDENT",
      "The target student is no longer active or eligible.",
    );
  }
  if (deny) {
    await tx.query(
      "UPDATE exception_requests SET status='denied' WHERE id=$1",
      [requestId],
    );
    await audit(
      tx,
      user,
      "exception.denied",
      "An exception was denied and will not be applied.",
      requestId,
    );
    return { message: "Request denied." };
  }
  const already = await row(
    tx,
    "SELECT 1 FROM request_approvals WHERE request_id=$1 AND approver_id=$2",
    [requestId, user.id],
  );
  assert(
    !already,
    409,
    "DUPLICATE_APPROVAL",
    "Your approval has already been recorded.",
  );
  await tx.query(
    "INSERT INTO request_approvals(request_id,approver_id) VALUES($1,$2)",
    [requestId, user.id],
  );
  const approvals = (
    await tx.query(
      `SELECT a.approver_id,p.active,p.roles FROM request_approvals a JOIN people p ON p.id=a.approver_id
    JOIN panel_members pm ON pm.person_id=p.id WHERE request_id=$1`,
      [requestId],
    )
  ).rows;
  assert(
    approvals.every((p) => p.active && p.roles.includes("approver")),
    409,
    "APPROVER_REVOKED",
    "An earlier approver is no longer eligible. Submit a new request.",
  );
  await audit(
    tx,
    user,
    "exception.approved",
    `An independent approval was recorded (${approvals.length}/2).`,
    requestId,
  );
  if (approvals.length < 2)
    return {
      message:
        "First approval recorded. One more independent approval is required.",
    };
  const data = request.data;
  if (request.kind === "panel") {
    const candidate = await row(
      tx,
      "SELECT roles,active FROM people WHERE id=$1",
      [data.candidateId],
    );
    assert(
      candidate?.active && candidate.roles.includes("approver"),
      409,
      "INELIGIBLE_CANDIDATE",
      "The replacement is no longer eligible.",
    );
    await tx.query("DELETE FROM panel_members WHERE person_id=$1", [
      data.replaceId,
    ]);
    await tx.query("INSERT INTO panel_members(person_id) VALUES($1)", [
      data.candidateId,
    ]);
    await tx.query(
      "UPDATE app_lock SET panel_version=panel_version+1 WHERE id=1",
    );
    await tx.query(
      "UPDATE exception_requests SET status='stale' WHERE status='pending' AND id<>$1",
      [requestId],
    );
  } else {
    if (request.kind === "force") {
      await tx.query(
        `INSERT INTO memberships(course_id,person_id,status) VALUES($1,$2,'enrolled')
        ON CONFLICT(course_id,person_id) DO UPDATE SET status='enrolled'`,
        [course.id, data.studentId],
      );
      await tx.query("UPDATE courses SET capacity=$2 WHERE id=$1", [
        course.id,
        data.resultingCapacity,
      ]);
    } else if (request.kind === "jump") {
      await tx.query(
        `UPDATE memberships SET sort_order=(SELECT COALESCE(min(sort_order),0)-1 FROM memberships WHERE course_id=$1)
        WHERE course_id=$1 AND person_id=$2`,
        [course.id, data.studentId],
      );
    } else {
      await tx.query(
        "DELETE FROM memberships WHERE course_id=$1 AND person_id=$2",
        [course.id, data.studentId],
      );
      await promote(tx, course);
    }
    await tx.query("UPDATE courses SET version=version+1 WHERE id=$1", [
      course.id,
    ]);
    await invalidateCourseRequests(tx, course.id, requestId);
  }
  await tx.query(
    "UPDATE exception_requests SET status='approved' WHERE id=$1",
    [requestId],
  );
  await audit(
    tx,
    user,
    "exception.applied",
    "An exception was applied once after two independent approvals. See the public exceptions list for its explanation.",
    requestId,
  );
  return {
    message: "Second approval recorded. The exception has been applied.",
  };
}
