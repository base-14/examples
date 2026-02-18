class Item < ApplicationRecord
  validates :title, presence: true
end
