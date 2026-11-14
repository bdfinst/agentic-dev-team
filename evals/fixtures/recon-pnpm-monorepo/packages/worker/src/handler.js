const axios = require("axios");

exports.handler = async (event) => {
  for (const record of event.Records) {
    const order = JSON.parse(record.body);
    await axios.post(`${process.env.SHIPPING_URL}/shipments`, { orderId: order.id });
  }
  return { ok: true };
};
