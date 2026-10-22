import express from "express";
import {
  signup,
  login,
  checkAuth,
  updateProfile,
  deleteUser,
} from "../controller/userController.js";
import { ProtectedRoute as protectedRoute } from "../middleware/auth.js";

const userRouter = express.Router();

// User creation/sign-in comes only from the verified FairEnrol Tide session.
userRouter.get("/check-auth", protectedRoute, checkAuth);
userRouter.put("/update-profile", protectedRoute, updateProfile);
userRouter.delete("/:userId", protectedRoute, deleteUser);

export default userRouter;
