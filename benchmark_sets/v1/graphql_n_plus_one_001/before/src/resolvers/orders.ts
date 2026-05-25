export const resolvers = {
  Query: {
    orders: async (_parent: unknown, _args: unknown, { db, loaders }: Context) => {
      const orders = await db.orders.list();
      const customers = await loaders.customer.loadMany(orders.map(order => order.customerId));
      return orders.map((order, index) => ({ ...order, customer: customers[index] }));
    },
  },
};

