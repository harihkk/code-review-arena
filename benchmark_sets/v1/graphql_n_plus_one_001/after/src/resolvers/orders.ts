export const resolvers = {
  Query: {
    orders: async (_parent: unknown, _args: unknown, { db }: Context) => {
      const orders = await db.orders.list();
      return Promise.all(
        orders.map(async order => ({
          ...order,
          customer: await db.customers.findById(order.customerId),
        })),
      );
    },
  },
};

