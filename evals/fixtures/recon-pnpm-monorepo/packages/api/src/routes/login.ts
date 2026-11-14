import bcrypt from "bcrypt";
import { Router } from "express";
import jwt from "jsonwebtoken";
import { findUser } from "@acme/shared";

export const loginRouter = Router();

loginRouter.post("/", async (req, res) => {
  const user = await findUser(req.body.email);
  if (!user || !(await bcrypt.compare(req.body.password, user.hash))) {
    return res.status(401).end();
  }
  const token = jwt.sign({ sub: user.id }, process.env.JWT_SECRET as string, { expiresIn: "15m" });
  res.json({ token });
});
