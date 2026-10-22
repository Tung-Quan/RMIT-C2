import "../lib/env.js";
import bcrypt from "bcryptjs";
import jwt from "jsonwebtoken";
import { uploadImageToS3 } from "../lib/s3Storage.js";
import { safeUser, usersRepo } from "../repositories/chatRepository.js";
import { io, userSocketMap } from "../server.js";

function getJwtSecret() {
  return process.env.JWT_SECRET || process.env.SECRET_KEY;
}

function publicUserData(user) {
  return {
    _id: user._id,
    id: user._id,
    username: user.username,
    email: user.email,
    profilePicture: user.profilePicture,
    bio: user.bio,
    createdAt: user.createdAt,
  };
}

export const signup = async (req, res) => {
  const { username, email, password, profilePicture, bio } = req.body;

  try {
    if (!username || !email || !password || !profilePicture) {
      return res.status(400).json({ message: "All fields are required" });
    }

    if (password.length < 6) {
      return res
        .status(400)
        .json({ message: "Password must be at least 6 characters long" });
    }
    if (!/\S+@\S+\.\S+/.test(email)) {
      return res.status(400).json({ message: "Invalid email format" });
    }
    if (username.length < 3) {
      return res
        .status(400)
        .json({ message: "Username must be at least 3 characters long" });
    }

    if (bio && bio.length > 150) {
      return res
        .status(400)
        .json({ message: "Bio cannot exceed 150 characters" });
    }

    const existingUser = await usersRepo.findByEmailOrUsername(email, username);
    if (existingUser) {
      return res
        .status(409)
        .json({ message: "Username or email already in use" });
    }

    const salt = await bcrypt.genSalt(10);
    const hashedPassword = await bcrypt.hash(password, salt);

    const storedProfilePicture = await uploadImageToS3(profilePicture, {
      folder: "profile-pictures",
      ownerId: email,
    });

    const newUser = await usersRepo.create({
      username,
      email,
      password: hashedPassword,
      profilePicture: storedProfilePicture,
      bio: bio || "",
    });

    const token = jwt.sign(
      { id: newUser._id, username: newUser.username, email: newUser.email },
      getJwtSecret(),
    );
    const newUserData = publicUserData(newUser);

    Object.values(userSocketMap).forEach((socketId) => {
      io.to(socketId).emit("newUser", newUserData);
    });

    res.status(201).json({
      success: true,
      userData: newUserData,
      token,
      message: "User registered successfully",
    });
  } catch (error) {
    console.error("Error during user signup:", error);
    res.status(500).json({
      success: false,
      message: "Server error during signup",
    });
  }
};

export const login = async (req, res) => {
  const { email, password } = req.body;
  try {
    if (!email || !password) {
      return res
        .status(400)
        .json({ message: "Email and password are required" });
    }
    const user = await usersRepo.findByEmail(email);
    if (!user) {
      return res.status(401).json({ message: "Invalid email or password" });
    }
    const isMatch = await bcrypt.compare(password, user.password);
    if (!isMatch) {
      return res.status(401).json({ message: "Invalid email or password" });
    }
    const token = jwt.sign(
      { id: user._id, username: user.username, email: user.email },
      getJwtSecret(),
    );
    res.status(200).json({
      success: true,
      userData: publicUserData(user),
      token,
      message: "Login successful",
    });
  } catch (error) {
    console.error("Error during user login:", error);
    res.status(500).json({
      success: false,
      message: "Server error during login",
    });
  }
};

export const checkAuth = (req, res) => {
  res.status(200).json({
    success: true,
    userData: req.user,
    message: "User is authenticated",
  });
};

export const deleteUser = async (req, res) => {
  try {
    const userId = req.user._id;
    const { userId: targetUserId } = req.params;

    if (userId !== targetUserId) {
      return res.status(403).json({
        success: false,
        message: "You can only delete your own account",
      });
    }

    await usersRepo.delete(userId);

    Object.values(userSocketMap).forEach((socketId) => {
      io.to(socketId).emit("userDeleted", { userId });
    });

    res.status(200).json({
      success: true,
      message: "Account deleted successfully",
    });
  } catch (error) {
    console.error("Error deleting user:", error);
    res.status(500).json({
      success: false,
      message: "Server error during account deletion",
    });
  }
};

export const updateProfile = async (req, res) => {
  try {
    const { username, bio, profilePicture } = req.body;
    const userId = req.user._id;
    const patch = { username, bio };

    if (profilePicture) {
      patch.profilePicture = await uploadImageToS3(profilePicture, {
        folder: "profile-pictures",
        ownerId: userId,
      });
    }

    const updatedData = await usersRepo.update(userId, patch);

    res.status(200).json({
      success: true,
      userData: safeUser(updatedData),
      message: "Profile updated successfully",
    });
  } catch (error) {
    console.error("Error updating user profile:", error);
    res.status(500).json({
      success: false,
      message: "Server error during profile update",
    });
  }
};
