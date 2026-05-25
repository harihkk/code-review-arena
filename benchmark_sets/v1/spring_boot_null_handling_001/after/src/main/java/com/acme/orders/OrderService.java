package com.acme.orders;

class OrderService {
    private OrderRepository repository;

    Order find(long id) {
        return repository.findById(id).get();
    }
}

