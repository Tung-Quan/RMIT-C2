import "dotenv/config";
import {
  postgresDatabase,
  initializeDatabase,
  linkIdentity,
} from "../server/db.js";
const [personId, subject] = process.argv.slice(2);
if (!personId || !subject)
  throw new Error(
    "Usage: npm run users:link -- <person-id> <verified-tide-subject>",
  );
const db = postgresDatabase(process.env.DATABASE_URL);
try {
  await initializeDatabase(db);
  await linkIdentity(db, {
    personId,
    subject,
    issuer: `${process.env.TIDECLOAK_URL}/realms/${process.env.TIDECLOAK_REALM}`,
  });
  console.log(
    `Linked identity to ${personId}. The Tide token must also carry the appropriate role.`,
  );
} finally {
  await db.close();
}
