import express from "express";
import { shipmentsRouter } from "./routes/shipments";

const app = express();
app.use(express.json());
app.use("/shipments", shipmentsRouter);

app.listen(4100);
