import jwt from "jsonwebtoken";

function getJwtSecret() {
  return process.env.JWT_SECRET || process.env.SECRET_KEY;
}

export function generateToken(user) {
  return jwt.sign(
    { id: user._id, username: user.username, email: user.email },
    getJwtSecret(),
    { expiresIn: "7d" },
  );
}
