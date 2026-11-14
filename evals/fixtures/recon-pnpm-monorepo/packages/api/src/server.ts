import express from "express";
import { loginRouter } from "./routes/login.js";

const app = express();
app.use(express.json());
app.use("/login", loginRouter);

app.listen(Number(process.env.PORT ?? 3000));
